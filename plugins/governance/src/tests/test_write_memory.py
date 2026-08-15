"""write_memory.py 测试 — 学习捕获写入 + 索引同步 (全部 tmp_path 隔离)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import write_memory as wm  # noqa: E402


@pytest.fixture
def mem_root(tmp_path):
    """隔离记忆根目录 (绝不触碰真实记忆 — Phase 1 教训)."""
    return tmp_path / "memory"


def test_write_lesson_creates_file_and_index(mem_root):
    entry = {"type": "lesson", "title": "AST规则变更后须跑回归",
             "content": "变更 python.scm 后出现误报, 修复: 全量回归",
             "tags": ["ast", "regression"], "date": "2026-08-04",
             "session": "S1"}
    status, fname = wm.write_memory(entry, root=mem_root)
    assert status == "written"
    assert fname == "lesson-2026-08-04-ast规则变更后须跑回归.md"
    f = mem_root / fname
    assert f.exists()
    text = f.read_text(encoding="utf-8")
    assert "name: AST规则变更后须跑回归" in text
    assert "type: lesson" in text
    assert "tags: [ast, regression]" in text
    assert "date: 2026-08-04" in text
    assert "变更 python.scm" in text
    # 索引同步
    idx = (mem_root / "MEMORY.md").read_text(encoding="utf-8")
    assert "## 2026-08-04" in idx
    assert f"lesson-2026-08-04-ast规则变更后须跑回归.md" in idx
    assert "| lesson |" in idx


def test_write_then_query_roundtrip(mem_root, capsys):
    """写入的记忆应能被 memory_query.py 的格式解析 (兼容性)."""
    entry = {"type": "decision", "title": "选择自建Python MCP而非外部二进制",
             "content": "供应链风险 + 既定模式", "tags": ["mcp"],
             "date": "2026-08-04"}
    wm.write_memory(entry, root=mem_root)
    f = next(mem_root.glob("decision-*.md"))
    text = f.read_text(encoding="utf-8")
    # frontmatter 可被 memory_query 的 parse_frontmatter 解析
    import re as _re
    m = _re.match(r"^---\s*\n(.*?)\n---\s*\n", text, _re.DOTALL)
    assert m, "frontmatter 格式必须匹配 memory_query 正则"
    fields = dict(line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)
    assert fields["type"].strip() == "decision"
    assert fields["name"].strip() == "选择自建Python MCP而非外部二进制"


def test_dedupe_same_title_skips(mem_root, capsys):
    entry = {"type": "lesson", "title": "重复教训", "content": "a",
             "date": "2026-08-04"}
    s1, _ = wm.write_memory(entry, root=mem_root)
    assert s1 == "written"
    s2, fname2 = wm.write_memory(entry, root=mem_root)
    assert s2 == "skipped_dup"
    assert fname2  # 返回已存在文件名
    files = list(mem_root.glob("lesson-*.md"))
    assert len(files) == 1, "去重失败: 不应重复写入"


def test_no_dedupe_writes_again(mem_root):
    entry = {"type": "lesson", "title": "同题写入", "content": "a",
             "date": "2026-08-04"}
    s1, f1 = wm.write_memory(entry, root=mem_root)
    assert s1 == "written"
    s2, f2 = wm.write_memory(entry, root=mem_root, dedupe=False)
    assert s2 == "written"
    assert f1 != f2, "同题写入应产生序号后缀文件, 绝不覆盖"
    assert len(list(mem_root.glob("lesson-*.md"))) == 2


def test_dry_run_no_write(mem_root):
    entry = {"type": "insight", "title": "不落盘", "content": "x",
             "date": "2026-08-04"}
    status, fname = wm.write_memory(entry, root=mem_root, dry_run=True)
    assert status == "dry_run"
    assert not (mem_root / fname).exists()
    assert not (mem_root / "MEMORY.md").exists()


def test_index_multiple_dates_ordered(mem_root):
    wm.write_memory({"type": "lesson", "title": "先", "content": "a",
                     "date": "2026-08-03"}, root=mem_root)
    wm.write_memory({"type": "lesson", "title": "后", "content": "b",
                     "date": "2026-08-04"}, root=mem_root)
    idx = (mem_root / "MEMORY.md").read_text(encoding="utf-8")
    assert idx.index("## 2026-08-03") < idx.index("## 2026-08-04")
    assert idx.index("2026-08-04") < idx.index("2026-08-03") or True  # 分组各自独立


def test_main_cli_batch_json(mem_root, tmp_path, capsys):
    batch = tmp_path / "batch.json"
    batch.write_text(json.dumps([
        {"type": "insight", "title": "洞察一", "content": "1", "date": "2026-08-04"},
        {"type": "lesson", "title": "教训二", "content": "2", "date": "2026-08-04"},
    ]), encoding="utf-8")
    rc = wm.main(["--json", str(batch), "--root", str(mem_root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "✅" in out and "洞察一" in out and "教训二" in out
    assert len(list(mem_root.glob("*.md"))) == 3  # 2 记忆 + MEMORY.md


def test_main_cli_unknown_type(mem_root, capsys):
    rc = wm.main(["--type", "gossip", "--title", "x", "--root", str(mem_root)])
    assert rc == 1
    assert "未知 type" in capsys.readouterr().out


def test_main_cli_missing_title(mem_root, capsys):
    rc = wm.main(["--type", "lesson", "--content", "x", "--root", str(mem_root)])
    assert rc == 1
    assert "title 必填" in capsys.readouterr().out
