"""Phase 0: memory_query.py 单元测试 (用 tmp_path 假记忆目录, 不触碰真实记忆)."""

import os
import pathlib
import subprocess
import sys

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "memory_query.py"


def _make_memory(root: pathlib.Path) -> pathlib.Path:
    """构造带 frontmatter + MEMORY.md 索引的假记忆目录, 返回目录。"""
    root.mkdir(parents=True, exist_ok=True)
    (root / "MEMORY.md").write_text(
        "## 2026-08-01\n"
        "- alpha.md | Alpha milestone | project | ...\n"
        "## 2026-08-02\n"
        "- beta.md | Beta lesson | project | ...\n",
        encoding="utf-8",
    )
    (root / "alpha.md").write_text(
        "---\nname: alpha\ndescription: Alpha milestone\n"
        "type: project\n---\n# Alpha\n关键内容 sql 注入\n",
        encoding="utf-8",
    )
    (root / "beta.md").write_text(
        "---\nname: beta\ndescription: Beta lesson\n"
        "type: project\n---\n# Beta\n超时陷阱\n",
        encoding="utf-8",
    )
    # 无索引日期 → 回退 mtime
    (root / "gamma.md").write_text(
        "---\nname: gamma\ndescription: Gamma decision\n"
        "type: decision\n---\n# Gamma\n",
        encoding="utf-8",
    )
    return root


def _run(root: pathlib.Path, *args):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        capture_output=True, text=True, encoding="utf-8", env=env,
    )


def test_type_filter(tmp_path):
    r = _run(_make_memory(tmp_path), "--type", "project", "--format", "plain")
    assert r.returncode == 0
    assert "alpha" in r.stdout and "beta" in r.stdout
    assert "gamma" not in r.stdout  # type=decision 被过滤


def test_date_range_from_index(tmp_path):
    r = _run(_make_memory(tmp_path), "--since", "2026-08-02", "--format", "plain")
    assert r.returncode == 0
    assert "alpha" not in r.stdout  # 索引日期 08-01 < 08-02
    assert "beta" in r.stdout  # 索引日期 08-02 命中
    assert "gamma" in r.stdout  # 无索引 → mtime(今天) 命中


def test_keyword_fulltext(tmp_path):
    r = _run(_make_memory(tmp_path), "--keyword", "sql", "--format", "plain")
    assert r.returncode == 0
    assert "alpha" in r.stdout  # body 含 "sql 注入"
    assert "beta" not in r.stdout


def test_keyword_case_insensitive(tmp_path):
    r = _run(_make_memory(tmp_path), "--keyword", "SQL", "--format", "plain")
    assert r.returncode == 0
    assert "alpha" in r.stdout


def test_combo_filter(tmp_path):
    r = _run(_make_memory(tmp_path), "--type", "project",
              "--since", "2026-08-01", "--until", "2026-08-01",
              "--keyword", "sql", "--format", "plain")
    assert r.returncode == 0
    assert "alpha" in r.stdout
    assert "beta" not in r.stdout  # until=08-01 排除 08-02


def test_no_match_returns_zero(tmp_path):
    r = _run(_make_memory(tmp_path), "--keyword", "不存在xyz")
    assert r.returncode == 0
    assert "无匹配" in r.stdout


def test_invalid_date_returns_two(tmp_path):
    r = _run(_make_memory(tmp_path), "--since", "2026-13-99")
    assert r.returncode == 2
    assert "YYYY-MM-DD" in r.stderr


def test_table_output_escapes_pipe(tmp_path):
    root = _make_memory(tmp_path)
    (root / "alpha.md").write_text(
        "---\nname: alpha\ndescription: 'a|b'\ntype: project\n---\nx\n",
        encoding="utf-8",
    )
    r = _run(root, "--keyword", "a")
    assert r.returncode == 0
    assert "a\\|b" in r.stdout  # pipe 被转义, 不破坏表格


# ---------- Phase 1 语义检索单元测试 (mock, 不依赖真实 Ollama) ----------

import pickle

SCRIPT_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import memory_query as mq


def _make_index(root: pathlib.Path, vectors):
    """构造 memory_index.pkl, vectors={filename: vector}。"""
    files = {
        name: {"vector": vec, "mtime_ns": 1, "meta": {
            "name": name, "type": "project", "date": "2026-08-01",
            "description": desc}}
        for name, vec, desc in vectors
    }
    (root / "memory_index.pkl").write_bytes(
        pickle.dumps({"model": "test-model", "files": files})
    )


def test_rrf_rank_ties_share_rank():
    """competition ranking: 并列分数取相同 rank (1, 2, 2, 4)。"""
    scores = [("a", 1.0), ("b", 0.5), ("c", 0.5), ("d", 0.0)]
    ranks = mq._rrf_rank(scores)
    assert ranks["a"] == 1
    assert ranks["b"] == ranks["c"] == 2  # 并列共享 rank
    assert ranks["d"] == 4  # 跳到下一个 rank


def test_semantic_search_orders_by_cosine(monkeypatch, tmp_path):
    """余弦相似度排序: 查询向量 [1,0] 应命中 [1,0] > [0.9,0.1] > [-1,0]。"""
    root = _make_memory(tmp_path)
    _make_index(root, [
        ("best.md", [1.0, 0.0], "best"),
        ("mid.md", [0.9, 0.1], "mid"),
        ("worst.md", [-1.0, 0.0], "worst"),
    ])
    monkeypatch.setenv("EMBED_MODEL", "test-model")
    monkeypatch.setattr(mq, "embed", lambda prompt, *a, **k: [1.0, 0.0])
    hits, reason = mq.semantic_search(root, "q", top=3)
    assert reason is None
    assert [name for _, name, _ in hits] == ["best.md", "mid.md", "worst.md"]
    assert hits[0][0] > hits[1][0] > hits[2][0]


def test_semantic_search_hybrid_keyword_boost(monkeypatch, tmp_path):
    """RRF 混合: 关键词 100% 命中的文件 (语义第3) 被顶到第一。

    双文件场景排名互补 (1↔2, 2↔1) RRF 得分必然平局, 故用 4 文件
    不对称排名验证关键词提升的真实行为。
    """
    root = _make_memory(tmp_path)
    _make_index(root, [
        ("sem_a.md", [0.95, 0.0], "无关内容A"),
        ("sem_b.md", [0.80, 0.0], "无关内容B"),
        ("kw.md", [0.55, 0.0], "策略演化引擎"),
        ("sem_c.md", [0.50, 0.0], "无关内容C"),
    ])
    monkeypatch.setenv("EMBED_MODEL", "test-model")
    monkeypatch.setattr(mq, "embed", lambda prompt, *a, **k: [1.0, 0.0])
    hits, reason = mq.semantic_search(root, "策略演化", top=4)
    assert reason is None
    # kw.md: 语义第3 + 关键词命中第一 → RRF 总分第一
    assert hits[0][1] == "kw.md"
    assert [name for _, name, _ in hits].index("kw.md") < \
        [name for _, name, _ in hits].index("sem_a.md") or hits[0][1] == "kw.md"


def test_semantic_search_no_index_degrades(tmp_path):
    """索引不存在 → 降级 (no_index), 不抛异常。"""
    root = _make_memory(tmp_path)  # 无 memory_index.pkl
    hits, reason = mq.semantic_search(root, "q", top=5)
    assert hits is None and reason == "no_index"


def test_semantic_search_model_mismatch(monkeypatch, tmp_path):
    """索引模型与当前不一致 → 降级 (model_mismatch)。"""
    root = _make_memory(tmp_path)
    _make_index(root, [("a.md", [1.0, 0.0], "a")])
    monkeypatch.setenv("EMBED_MODEL", "other-model")
    hits, reason = mq.semantic_search(root, "q", top=5)
    assert hits is None and reason.startswith("model_mismatch")


def test_embed_calls_ollama_and_parses(monkeypatch):
    """embed() 正确调用 Ollama 并解析 embedding。"""
    import json
    import urllib.request

    captured = {}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"embedding": [1.0, 2.0]}).encode()

    def fake_urlopen(req, timeout=30):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data)
        return FakeResp()

    monkeypatch.setenv("OLLAMA_URL", "http://mock:11434")
    monkeypatch.setenv("EMBED_MODEL", "nomic-embed-text")  # 防外部 env 污染
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    vec = mq.embed("测试")
    assert vec == [1.0, 2.0]
    assert captured["url"] == "http://mock:11434/api/embeddings"
    assert captured["body"]["model"] == "nomic-embed-text"  # 默认模型


def test_embed_failure_returns_none(monkeypatch):
    """Ollama 不可用 → embed 返回 None (不抛异常)。"""
    import urllib.request

    def boom(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setenv("OLLAMA_URL", "http://localhost:1")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert mq.embed("测试") is None


def test_cosine_basics():
    assert mq.cosine([1, 0], [1, 0]) == 1.0
    assert abs(mq.cosine([1, 0], [0, 1])) < 1e-9  # 正交 = 0
    assert mq.cosine([1, 0], [-1, 0]) == -1.0
    assert mq.cosine([], []) == 0.0  # 空向量安全
    assert mq.cosine([1, 0], [1, 0, 0]) == 0.0  # 维度不一致安全


# ---------- vectorize_memory.py 单元测试 (mock, 不依赖真实 Ollama) ----------

import vectorize_memory as vm


def _vm_index(root, model="test-model"):
    """预生成索引 (覆盖 _make_memory 的全部 3 个文件), 返回 {name: mtime_ns}。"""
    files = {}
    for name, vec in [("alpha.md", [1.0]), ("beta.md", [0.5]), ("gamma.md", [0.2])]:
        p = root / name
        files[name] = {"vector": vec, "mtime_ns": p.stat().st_mtime_ns,
                       "meta": {"name": name, "type": "project", "date": "2026-08-01"}}
    (root / "memory_index.pkl").write_bytes(
        pickle.dumps({"model": model, "files": files})
    )
    return files


def test_vectorize_incremental_skips_unchanged(monkeypatch, tmp_path):
    """增量: mtime 未变的文件不重新嵌入。"""
    root = _make_memory(tmp_path)  # alpha.md + beta.md
    _vm_index(root)
    monkeypatch.setenv("EMBED_MODEL", "test-model")
    calls = []

    def fake_embed(prompt, *a, **k):
        calls.append(prompt)
        return [0.1, 0.2]

    monkeypatch.setattr(vm, "embed", fake_embed)
    rc = vm.main(["--root", str(root)])
    assert rc == 0
    assert calls == []  # 索引已最新, 零嵌入调用


def test_vectorize_model_change_forces_rebuild(monkeypatch, tmp_path):
    """模型变更 → 强制全量重建 (旧向量不可比)。"""
    root = _make_memory(tmp_path)
    _vm_index(root, model="old-model")
    monkeypatch.setenv("EMBED_MODEL", "new-model")
    calls = []

    def fake_embed(prompt, *a, **k):
        calls.append(prompt)
        return [0.1] * 1024

    monkeypatch.setattr(vm, "embed", fake_embed)
    rc = vm.main(["--root", str(root)])
    assert rc == 0
    assert len(calls) == 4
    # 索引模型已更新
    with open(root / "memory_index.pkl", "rb") as f:
        data = pickle.load(f)
    assert data["model"] == "new-model"


def test_vectorize_ollama_down_returns_one(monkeypatch, tmp_path):
    """Ollama 不可用 → exit 1, 不写索引。"""
    root = _make_memory(tmp_path)
    monkeypatch.setenv("EMBED_MODEL", "test-model")
    monkeypatch.setattr(vm, "embed", lambda prompt, *a, **k: None)
    rc = vm.main(["--root", str(root)])
    assert rc == 1
    assert not (root / "memory_index.pkl").exists()


def test_vectorize_build_prompt_truncates():
    """build_prompt 截断至 MAX_CHARS。"""
    entry = {"name": "n", "description": "d", "body": "x" * (vm.MAX_CHARS + 100)}
    prompt = vm.build_prompt(entry)
    assert len(prompt) <= vm.MAX_CHARS
    assert prompt.startswith("n\nd\n")
