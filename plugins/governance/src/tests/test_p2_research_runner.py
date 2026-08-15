"""scripts/p2_research_runner.py 测试。

策略: 不依赖真实 gpt_researcher 包 (Py>=3.12 隔离环境, 本测试跑在
.venv-b1 Python 3.11) —— 通过 sys.modules 注入假 gpt_researcher 模块
验证编排逻辑 (参数传递 / JSON 输出 / 错误路径)。.env 解析用 tmp_path。
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


@pytest.fixture(autouse=True)
def _redirect_output_dir(tmp_path, monkeypatch):
    """落盘协议 (P0) 引入后, main() 会真实写 research_outputs/ —
    autouse 重定向到临时目录, 防测试污染仓库。"""
    monkeypatch.setattr(runner, "_OUTPUT_DIR", tmp_path)
    yield


class _FakeResearcher:
    """模拟 gpt_researcher.GPTResearcher。"""

    def __init__(self, query, report_type="research_report", verbose=True):
        self.query = query
        self.report_type = report_type
        self.verbose = verbose
        self.context = [{"url": "https://example.com/1"}, {"url": "https://example.com/2"}]
        self.source_urls = {"https://example.com/1", "https://example.com/2"}

    async def conduct_research(self):
        self._done = True

    async def write_report(self):
        return f"# 报告\n主题: {self.query} / 类型: {self.report_type}"


class _FakeModule(types.ModuleType):
    """可导入的假 gpt_researcher 包。"""

    GPTResearcher = _FakeResearcher


def _install_fake_gpt(monkeypatch):
    mod = _FakeModule("gpt_researcher")
    monkeypatch.setitem(sys.modules, "gpt_researcher", mod)


# ── .env 解析 ──────────────────────────────────────────────────────────

def test_load_env_parses_keys_and_quotes(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "# 注释行\nDEEPSEEK_API_KEY=\"sk-test-123\"\nFAST_LLM=deepseek:deepseek-chat\n"
        "EMPTY=\n", encoding="utf-8")
    for k in ("DEEPSEEK_API_KEY", "FAST_LLM"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("FAST_LLM", "pre-existing")
    runner.load_env(env)
    assert os_environ("DEEPSEEK_API_KEY") == "sk-test-123"
    # 已存在的环境变量不被覆盖
    assert os_environ("FAST_LLM") == "pre-existing"


def os_environ(key):
    import os
    return os.environ.get(key)


def test_load_env_missing_file_silent(tmp_path):
    runner.load_env(tmp_path / "nope.env")  # 不应抛异常


def test_load_env_no_override_existing(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("KEY_A=from-file\nKEY_B=from-file\n", encoding="utf-8")
    monkeypatch.setenv("KEY_B", "from-env")
    monkeypatch.delenv("KEY_A", raising=False)
    runner.load_env(env)
    assert os_environ("KEY_A") == "from-file"
    assert os_environ("KEY_B") == "from-env"


# ── 成功路径 (假 gpt_researcher) ──────────────────────────────────────

def test_main_success_json_output(monkeypatch, capsys):
    _install_fake_gpt(monkeypatch)
    rc = runner.main(["--query", "AI governance", "--report-type", "summary"])
    out = capsys.readouterr().out.strip()
    assert rc == 0
    data = json.loads(out)
    assert data["ok"] is True
    assert "AI governance" in data["report"]
    assert data["sources"] == 2  # context 列表长度
    assert data["report_type"] == "research_report"  # summary 已归一化


def test_main_default_report_type(monkeypatch, capsys):
    _install_fake_gpt(monkeypatch)
    rc = runner.main(["--query", "tree-sitter"])
    data = json.loads(capsys.readouterr().out.strip())
    assert data["ok"] is True
    assert data["report_type"] == "research_report"


def test_main_max_sources_accepted(monkeypatch, capsys):
    _install_fake_gpt(monkeypatch)
    rc = runner.main(["--query", "x", "--max-sources", "20"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out.strip())
    assert data["ok"] is True


def test_main_agent_created_verbose_false(monkeypatch, capsys):
    """gpt-researcher 必须 verbose=False — 否则无 websocket 时把整份报告
    print 到 stdout, 污染 MCP 单行 JSON 契约 (2026-08-04 实证踩坑)。"""
    _install_fake_gpt(monkeypatch)
    captured = {}

    class _Recording(_FakeResearcher):
        def __init__(self, query, report_type="research_report", verbose=True):
            super().__init__(query, report_type, verbose)
            captured["verbose"] = verbose

    mod = _FakeModule("gpt_researcher")
    mod.GPTResearcher = _Recording
    monkeypatch.setitem(sys.modules, "gpt_researcher", mod)
    runner.main(["--query", "x"])
    assert captured.get("verbose") is False


# ── 错误路径 ──────────────────────────────────────────────────────────

def test_main_gpt_missing_readable_error(monkeypatch, capsys):
    # 模拟真实导入失败: sys.modules 置 None 使 from gpt_researcher import ... 抛
    # ImportError, runner 的真实 _gpt_researcher_cls 会包装可读消息 (含部署提示)
    monkeypatch.setitem(sys.modules, "gpt_researcher", None)
    rc = runner.main(["--query", "x"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out.strip())
    assert data["ok"] is False
    assert "deploy_p2_research.ps1" in data["error"]


def test_main_research_failure_readable(monkeypatch, capsys):
    """conduct_research 抛异常 → 可读错误 JSON, 非 traceback。"""
    class _Boom:
        def __init__(self, query, report_type="research_report", verbose=True):
            self.query = query

        async def conduct_research(self):
            raise RuntimeError("上游 API 超时")

        async def write_report(self):
            return ""

    mod = _FakeModule("gpt_researcher")
    mod.GPTResearcher = _Boom
    monkeypatch.setitem(sys.modules, "gpt_researcher", mod)
    rc = runner.main(["--query", "x"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out.strip())
    assert data["ok"] is False
    assert "研究执行失败" in data["error"]
    assert "RuntimeError" in data["error"]


# ── CONFIG_PATH 锚定 ──────────────────────────────────────────────────

def test_main_config_path_relative_resolved(monkeypatch, capsys, tmp_path):
    """相对 CONFIG_PATH 应锚定到仓库根 (不依赖 CWD)。"""
    import os
    _install_fake_gpt(monkeypatch)
    # 指向仓库内真实存在的 config/gptr_local.json
    runner.load_env = lambda _p=None: None  # 禁用真实 .env, 隔离
    os.environ.pop("CONFIG_PATH", None)
    monkeypatch.setenv("CONFIG_PATH", "config/gptr_local.json")
    runner.main(["--query", "x"])
    resolved = os.environ.get("CONFIG_PATH", "")
    assert resolved.startswith(str(runner._REPO_ROOT))
    assert resolved.endswith("gptr_local.json")
    assert os.path.isabs(resolved)

def test_main_config_path_missing_readable(monkeypatch, capsys):
    """CONFIG_PATH 指向不存在的文件 → 可读错误 JSON。"""
    import os
    _install_fake_gpt(monkeypatch)
    runner.load_env = lambda _p=None: None
    os.environ.pop("CONFIG_PATH", None)
    monkeypatch.setenv("CONFIG_PATH", "config/definitely_missing.json")
    rc = runner.main(["--query", "x"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out.strip())
    assert data["ok"] is False
    assert "CONFIG_PATH 不存在" in data["error"]


# ── CLI 参数校验 ──────────────────────────────────────────────────────

def test_main_requires_query():
    with pytest.raises(SystemExit):
        runner.main([])


def test_main_invalid_report_type():
    with pytest.raises(SystemExit):
        runner.main(["--query", "x", "--report-type", "bogus"])
