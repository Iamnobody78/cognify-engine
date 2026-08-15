"""knowledge_distill.py 测试 — 启发式知识蒸馏 (tmp_path 隔离)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import knowledge_distill as kd  # noqa: E402


def _mk(root, fname, type_, title, tags, content, date="2026-08-04", session="S1"):
    root.mkdir(parents=True, exist_ok=True)
    (root / fname).write_text(
        f"---\nname: {title}\ntype: {type_}\ntags: [{', '.join(tags)}]\n"
        f"date: {date}\nsession: {session}\n---\n\n{content}\n",
        encoding="utf-8")


@pytest.fixture
def mem_root(tmp_path):
    root = tmp_path / "memory"
    # 3 条 lesson 共享 tag:ast + 关键词回归; 1 条 decision 不同 tag
    _mk(root, "lesson-1.md", "lesson", "AST规则变更后误报", ["ast", "regression"],
        "变更 python.scm 后出现误报, 修复: 全量回归 pytest tests/test_ast_guard.py")
    _mk(root, "lesson-2.md", "lesson", "CI超时导致构建失败", ["ast", "ci", "timeout"],
        "CI 超时, 拆分测试到多个 job 并加 --timeout")
    _mk(root, "lesson-3.md", "lesson", "AST节点变更回归", ["ast"],
        "回归测试必须运行, 避免误报")
    _mk(root, "decision-1.md", "decision", "选择MCP自建方案", ["mcp"],
        "外部二进制供应链风险, 自建 Python MCP")
    return root


def test_load_memories_skips_index(mem_root):
    (mem_root / "MEMORY.md").write_text("# idx\n", encoding="utf-8")
    ms = kd.load_memories(mem_root)
    assert len(ms) == 4
    assert all(m["file"] != "MEMORY.md" for m in ms)
    types = {m["type"] for m in ms}
    assert types == {"lesson", "decision"}


def test_distill_patterns_ast_dominant(mem_root):
    patterns, preferences, stats = kd.distill(mem_root, tmp := Path(mem_root).parent / "out")
    # ast tag 出现 3 次 → 必在 patterns
    ast_pat = [p for p in patterns if p["pattern"] == "tag:ast"]
    assert ast_pat and ast_pat[0]["count"] == 3
    assert ast_pat[0]["last_occurrence"] == "2026-08-04"
    # 关键词回归 (3 条 lesson 中 ≥2 命中) → 应有建议
    fix_pats = [p["suggested_fix"] for p in patterns]
    assert any("回归" in f for f in fix_pats)
    assert stats["total"] == 4
    assert stats["by_type"]["lesson"] == 3


def test_distill_preferences(mem_root):
    _, preferences, _ = kd.distill(mem_root, mem_root.parent / "out")
    assert preferences["dominant_type"] == "lesson"
    assert preferences["top_tags"][0][0] == "ast"
    assert "S1" in preferences["sessions_seen"]


def test_write_outputs_yaml(mem_root, tmp_path):
    patterns, preferences, stats = kd.distill(mem_root, str(tmp_path / "out"))
    files = kd.write_outputs(patterns, preferences, stats, str(tmp_path / "out"))
    assert set(files) == {"patterns.yaml", "preferences.yaml"}
    p = (tmp_path / "out" / "patterns.yaml").read_text(encoding="utf-8")
    assert "failure_patterns:" in p and "suggested_fix:" in p
    pref = (tmp_path / "out" / "preferences.yaml").read_text(encoding="utf-8")
    assert "dominant_type: lesson" in pref


def test_main_json_report(mem_root, tmp_path, capsys):
    rc = kd.main(["--root", str(mem_root), "--json", "--top-k", "5"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out.strip())
    assert data["stats"]["total"] == 4
    assert any(p["pattern"] == "tag:ast" for p in data["patterns"])


def test_quoted_list_style_tags(tmp_path):
    """真实记忆使用 YAML 列表风格 tags: ["a", "b"] → 引号必须剥离。"""
    root = tmp_path / "memory"
    root.mkdir()
    (root / "m1.md").write_text(
        "---\nname: quoted-tags\ntype: project\ntags: [\"kalman-filter\", \"cql\", \"bottlesumo\"]\n"
        "date: 2026-08-04\n---\n\ncontent with 回归 issue\n", encoding="utf-8")
    ms = kd.load_memories(root)
    assert ms[0]["tags"] == ["kalman-filter", "cql", "bottlesumo"]
    assert all('"' not in t and "'" not in t for t in ms[0]["tags"])


def test_load_train_patterns_strips_quotes(tmp_path):
    """patterns.yaml 的值带引号 → load_train_patterns 必须剥离, 否则共现=0。"""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import benchmark_distill as bd
    y = tmp_path / "patterns.yaml"
    y.write_text(
        "# 注释\nfailure_patterns:\n"
        "  - pattern: \"keyword:路径\"\n"
        "    count: 27\n"
        "    last_occurrence: \"2026-08-04\"\n"
        "    suggested_fix: \"脚本/测试应使用绝对路径或锚定仓库根, 不依赖 CWD\"\n"
        "  - pattern: \"keyword:timeout\"\n"
        "    count: 19\n"
        "    last_occurrence: \"2026-08-03\"\n"
        "    suggested_fix: \"涉及外部进程/网络的测试需显式 --timeout 并留足余量\"\n",
        encoding="utf-8")
    pats, fixes = bd.load_train_patterns(y)
    assert pats == ["keyword:路径", "keyword:timeout"]
    assert fixes == {"脚本/测试应使用绝对路径或锚定仓库根, 不依赖 CWD",
                     "涉及外部进程/网络的测试需显式 --timeout 并留足余量"}
    assert all('"' not in f for f in fixes)


def test_main_writes_files(mem_root, tmp_path, capsys):
    out = tmp_path / "kout"
    rc = kd.main(["--root", str(mem_root), "--out", str(out)])
    assert rc == 0
    assert (out / "patterns.yaml").exists()
    assert (out / "preferences.yaml").exists()
    assert "蒸馏完成" in capsys.readouterr().out


def test_parse_frontmatter_strips_quotes(tmp_path):
    root = tmp_path / "m"
    root.mkdir()
    (root / "q.md").write_text(
        '---\ntype: "project"\nname: 引号类型\ntags: []\ndate: 2026-08-04\n---\n\nx\n',
        encoding="utf-8")
    ms = kd.load_memories(root)
    assert len(ms) == 1
    assert ms[0]["type"] == "project", "带引号 type 应剥离"


def test_empty_root(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    patterns, preferences, stats = kd.distill(empty, tmp_path / "out")
    assert stats["total"] == 0
    assert patterns == []
    assert preferences["dominant_type"] == "none"
