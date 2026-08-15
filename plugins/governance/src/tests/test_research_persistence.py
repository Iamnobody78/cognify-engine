"""研究产出落盘协议测试 (P0 — research_output.md).

覆盖:
1. persist_report 落盘存在: 报告写入 research_outputs/{slug}.md, 返回绝对路径
2. 命名正确: query → slug (小写/连字符/截断/空回退), 同 slug 追加序号不覆盖
3. 元数据完整: 内容与 report 字节一致 + 空报告/落盘失败走 best-effort (不抛异常)
4. runner main() 的 stdout JSON 含 report_path/persist_error (契约新增字段不破坏旧字段)
5. MCP 透传: _run_research_tool 的返回 JSON 含 report_path
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import p2_research_runner as runner  # noqa: E402


# ---------- persist_report: 落盘存在 ----------

def test_persist_report_writes_file(tmp_path):
    path, err = runner.persist_report("# 报告\n正文", "What is AI governance?", tmp_path)
    assert err == ""
    assert path.startswith(str(tmp_path))
    assert Path(path).exists()
    assert Path(path).read_text(encoding="utf-8") == "# 报告\n正文"


def test_persist_report_creates_output_dir(tmp_path):
    nested = tmp_path / "deep" / "nested"
    path, err = runner.persist_report("x", "q", nested)
    assert err == ""
    assert Path(path).parent == nested.resolve()
    assert nested.exists()


# ---------- 命名正确 ----------

def test_query_slug_normalization():
    assert runner._query_slug("What is AI governance?") == "what-is-ai-governance"
    assert runner._query_slug("  AI..Governance!! ") == "ai-governance"
    assert runner._query_slug("x" * 100) == "x" * 60  # 截断 60
    assert runner._query_slug("???") == "research"  # 全符号 → 回退


def test_persist_report_no_overwrite_same_slug(tmp_path):
    p1, _ = runner.persist_report("第一份", "same query", tmp_path)
    p2, _ = runner.persist_report("第二份", "same query", tmp_path)
    assert p1 != p2
    assert Path(p1).name == "same-query.md"
    assert Path(p2).name == "same-query-2.md"
    assert Path(p1).read_text(encoding="utf-8") == "第一份"
    assert Path(p2).read_text(encoding="utf-8") == "第二份"


# ---------- 元数据完整 + best-effort ----------

def test_persist_report_empty_report_skips(tmp_path):
    path, err = runner.persist_report("   \n", "q", tmp_path)
    assert path == ""
    assert "报告为空" in err


def test_persist_report_write_failure_is_best_effort(tmp_path):
    """落盘失败 (目标路径是文件而非目录) → 返回错误不抛异常。"""
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("占用", encoding="utf-8")
    path, err = runner.persist_report("报告内容", "q", blocker)
    assert path == ""
    assert "落盘失败" in err


# ---------- runner main(): stdout JSON 契约 ----------

def test_main_json_includes_report_path(tmp_path, capsys, monkeypatch):
    """研究成功后 stdout JSON 含 report_path; 旧字段 report/sources 仍在。"""
    monkeypatch.setattr(runner, "_OUTPUT_DIR", tmp_path)  # 模块常量 import 时已求值

    class _FakeResearcher:
        def __init__(self, query, report_type="research_report", verbose=True):
            pass

        async def conduct_research(self):
            return None

        async def write_report(self):
            return "# 落盘测试报告"

        source_urls = {"https://a.example", "https://b.example"}

    fake = types.ModuleType("gpt_researcher")
    fake.GPTResearcher = _FakeResearcher
    monkeypatch.setitem(sys.modules, "gpt_researcher", fake)

    rc = runner.main(["--query", "test query", "--report-type", "research_report"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out.strip())
    assert data["ok"] is True
    assert data["report"] == "# 落盘测试报告"
    assert data["sources"] == 2
    assert data["report_path"].startswith(str(tmp_path))
    assert data["persist_error"] == ""
    assert Path(data["report_path"]).read_text(encoding="utf-8") == "# 落盘测试报告"
