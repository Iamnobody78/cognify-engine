"""Phase 2: session_summarize.py 单元测试 (tmp_path 假记忆目录, 不触碰真实记忆)."""

import os
import pathlib
import subprocess
import sys

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT))
import session_summarize as ss


def _make_memory(root: pathlib.Path, n: int = 3) -> pathlib.Path:
    """构造 n 个带 frontmatter + MEMORY.md 索引的假记忆文件。"""
    root.mkdir(parents=True, exist_ok=True)
    index = []
    for i in range(1, n + 1):
        d = f"2026-08-{i:02d}"
        index.append(f"## {d}\n- f{i:02d}.md | Memory file {i} | project | ...\n")
        (root / f"f{i:02d}.md").write_text(
            f"---\nname: f{i:02d}\ndescription: Memory file {i}\ntype: project\n"
            f"---\n# F{i}\n",
            encoding="utf-8",
        )
    (root / "MEMORY.md").write_text("".join(index), encoding="utf-8")
    return root


# ---------- recover: 启动恢复摘要 ----------

def test_recover_prints_context(tmp_path, capsys):
    root = _make_memory(tmp_path)
    assert ss.recover(root) == 0
    out = capsys.readouterr().out
    assert "已恢复上下文: 3 记忆文件" in out
    assert "最近会话 2026-08-03" in out  # 索引日期最大值
    assert "f03.md" in out


def test_recover_limit_and_order(tmp_path, capsys):
    root = _make_memory(tmp_path, n=7)
    ss.recover(root, limit=3)
    out = capsys.readouterr().out
    # 最新 3 条在, 更旧的被省略
    for name in ("f07.md", "f06.md", "f05.md"):
        assert name in out
    assert "f04.md" not in out and "f01.md" not in out
    assert "其余 4 条" in out
    assert out.index("f07.md") < out.index("f06.md") < out.index("f05.md")


def test_recover_missing_index_falls_back(tmp_path, capsys):
    """无 MEMORY.md → 回退 mtime 日期, 仍可恢复。"""
    root = tmp_path
    for i in (1, 2, 3):
        (root / f"f{i}.md").write_text(
            f"---\nname: f{i}\ndescription: d{i}\ntype: project\n---\nx\n",
            encoding="utf-8")
    assert ss.recover(root) == 0
    out = capsys.readouterr().out
    assert "已恢复上下文: 3 记忆文件" in out
    assert all(f"f{i}.md" in out for i in (1, 2, 3))


def test_recover_empty_dir(tmp_path, capsys):
    (tmp_path / "MEMORY.md").write_text("# 空索引\n", encoding="utf-8")
    assert ss.recover(tmp_path) == 0
    assert "0 记忆文件" in capsys.readouterr().out


def test_recover_missing_root(tmp_path, capsys):
    assert ss.main(["recover", "--root", str(tmp_path / "nope")]) == 2
    assert "记忆目录不存在" in capsys.readouterr().err


def test_recover_truncates_description(tmp_path, capsys):
    root = tmp_path
    (root / "long.md").write_text(
        "---\nname: long\ndescription: " + "x" * 200 + "\ntype: project\n---\n# L\n",
        encoding="utf-8")
    ss.recover(root)
    out = capsys.readouterr().out
    assert "…" in out
    assert out.count("x") == ss.DESC_MAX  # 描述截断至 120


# ---------- summarize: 会话结束写入 ----------

def test_summarize_writes_session_file(tmp_path, capsys):
    root = tmp_path
    rc = ss.main(["summarize", "--root", str(root), "--date", "2026-08-01",
                  "--title", "测试会话", "--summary", "完成了 Phase 2",
                  "--decisions", "决策A", "--todos", "事项B"])
    assert rc == 0
    p = root / "session_2026-08-01.md"
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    assert "name: session_2026-08-01" in text  # 文件名用下划线
    assert "type: session" in text
    assert "## 对话概要" in text and "完成了 Phase 2" in text
    assert "## 关键决策" in text and "决策A" in text
    assert "## 待办事项" in text and "事项B" in text
    assert "✅ 会话记录已写入: session_2026-08-01.md" in capsys.readouterr().out


def test_summarize_same_day_suffix(tmp_path, capsys):
    """同日多会话: 基础名被占 → 追加时间后缀, 原文件不被覆盖。"""
    root = tmp_path
    assert ss.main(["summarize", "--root", str(root), "--date", "2026-08-01",
                    "--time", "0001", "--summary", "s1"]) == 0
    assert ss.main(["summarize", "--root", str(root), "--date", "2026-08-01",
                    "--time", "0002", "--summary", "s2"]) == 0
    assert (root / "session_2026-08-01.md").exists()
    assert (root / "session_2026-08-01_0002.md").exists()
    assert "s1" in (root / "session_2026-08-01.md").read_text(encoding="utf-8")
    assert "s2" in (root / "session_2026-08-01_0002.md").read_text(encoding="utf-8")


def test_summarize_from_files(tmp_path, capsys):
    """长文本经 --*-file 注入 (绕开命令行长度/编码限制)。"""
    root = tmp_path
    (root / "s.txt").write_text("概要内容", encoding="utf-8")
    (root / "d.txt").write_text("决策内容", encoding="utf-8")
    (root / "t.txt").write_text("待办内容", encoding="utf-8")
    rc = ss.main(["summarize", "--root", str(root), "--date", "2026-08-02",
                  "--summary-file", str(root / "s.txt"),
                  "--decisions-file", str(root / "d.txt"),
                  "--todos-file", str(root / "t.txt")])
    assert rc == 0
    text = (root / "session_2026-08-02.md").read_text(encoding="utf-8")
    assert all(x in text for x in ("概要内容", "决策内容", "待办内容"))


def test_summarize_missing_content_file(tmp_path, capsys):
    root = tmp_path
    rc = ss.main(["summarize", "--root", str(root), "--date", "2026-08-01",
                  "--summary-file", str(root / "nope.txt")])
    assert rc == 2
    assert "读取" in capsys.readouterr().err


def test_summarize_no_content(tmp_path, capsys):
    root = tmp_path
    rc = ss.main(["summarize", "--root", str(root), "--date", "2026-08-01"])
    assert rc == 2
    assert "无可写入内容" in capsys.readouterr().err
    assert not list(root.glob("session_*.md"))


def test_summarize_bad_date(tmp_path, capsys):
    root = tmp_path
    rc = ss.main(["summarize", "--root", str(root), "--date", "2026-13-99",
                  "--summary", "x"])
    assert rc == 2
    assert "YYYY-MM-DD" in capsys.readouterr().err


def test_summarize_missing_root(tmp_path, capsys):
    assert ss.main(["summarize", "--root", str(tmp_path / "nope")]) == 2


# ---------- CLI 冒烟 (subprocess, 验证编码与入口) ----------

def _run(root: pathlib.Path, *args):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, str(SCRIPT / "session_summarize.py"), "--root", str(root), *args],
        capture_output=True, text=True, encoding="utf-8", env=env,
    )


def test_cli_recover_subprocess(tmp_path):
    root = _make_memory(tmp_path)
    r = _run(root, "recover")
    assert r.returncode == 0
    assert "已恢复上下文" in r.stdout


def test_cli_summarize_subprocess(tmp_path):
    root = tmp_path
    r = _run(root, "summarize", "--date", "2026-08-03", "--summary", "CLI 测试")
    assert r.returncode == 0
    assert (root / "session_2026-08-03.md").exists()
    assert "✅" in r.stdout  # UTF-8 编码正常, 非 cp950 乱码
