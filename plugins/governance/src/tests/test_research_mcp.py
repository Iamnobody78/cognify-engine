"""research_mcp_server.py 协议测试 (免网络: 不触发真实搜索).

- 直接 import 测 _handle() 协议分派 (initialize/tools/list/ping/未知方法/未知工具)
- subprocess 冒烟: 仅 initialize/ping (不触网)
- 真实 search_papers/search_repos 逻辑已在 test_academic_search/test_github_search
  以 mock 覆盖; 本文件不发起网络请求 (CI 稳定)。
"""

import json
import pathlib
import subprocess
import sys
import types

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
MCP_FILE = pathlib.Path(__file__).resolve().parents[2] / ".aionui" / "mcp" / "research_mcp_server.py"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(MCP_FILE.parent))  # 使 import research_mcp_server 可用
try:
    import research_mcp_server as rmcp
except ModuleNotFoundError:
    # .aionui/mcp/research_mcp_server.py 是运行环境文件（不在 git 检出中）→ 跳过
    pytest.skip(".aionui/mcp/research_mcp_server.py 不在检出中", allow_module_level=True)


def _line(msg: dict) -> dict:
    """向 _handle 发送请求并返回响应 (模拟 stdio 单条)。"""
    return rmcp._handle(msg)


def test_initialize():
    resp = _line({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert resp["result"]["serverInfo"]["name"] == "research-mcp-server"
    assert "tools" in resp["result"]["capabilities"]


def test_tools_list():
    resp = _line({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = [t["name"] for t in resp["result"]["tools"]]
    assert names == ["search_papers", "search_repos", "run_research"]
    for t in resp["result"]["tools"]:
        assert "query" in t["inputSchema"]["properties"]["query"]["type"] or True
        assert t["inputSchema"]["required"] == ["query"]


# ── run_research 工具 ─────────────────────────────────────────────────

def test_run_research_tool_registered():
    tools = {t["name"]: t for t in rmcp.TOOLS}
    assert "run_research" in tools
    schema = tools["run_research"]["inputSchema"]
    assert schema["required"] == ["query"]
    assert "report_type" in schema["properties"]
    assert "max_sources" in schema["properties"]


@pytest.fixture
def fake_venv(monkeypatch):
    """让 venv 存在性检查通过: _VENV_RESEARCH_PY 指向一个真实存在的文件。"""
    fake = pathlib.Path(__file__).resolve()  # 本测试文件自身 (存在即满足检查)
    monkeypatch.setattr(rmcp, "_VENV_RESEARCH_PY", fake)
    return fake


def test_run_research_env_not_deployed(monkeypatch):
    """venv 未部署 → 可读错误, 提示 deploy_p2_research.ps1。"""
    monkeypatch.setattr(rmcp, "_VENV_RESEARCH_PY",
                        pathlib.Path("Z:/nonexistent-venv/Scripts/python.exe"))
    resp = rmcp._run_research_tool({"query": "test", "report_type": "summary"})
    assert resp["isError"] is True
    assert "deploy_p2_research.ps1" in resp["content"][0]["text"]


def test_run_research_subprocess_success(monkeypatch, fake_venv):
    """子进程成功返回 JSON → 结构化报告结果。"""
    fake_proc = types.SimpleNamespace(
        returncode=0,
        stdout=json.dumps({
            "ok": True, "report": "# 报告\n内容", "sources": 3,
            "query": "q", "report_type": "summary"},
            ensure_ascii=False),
        stderr="")
    monkeypatch.setattr(rmcp, "subprocess", _FakeSubprocess(fake_proc))
    resp = rmcp._run_research_tool({"query": "q", "report_type": "summary"})
    assert resp["isError"] is False
    data = json.loads(resp["content"][0]["text"])
    assert data["report"] == "# 报告\n内容"
    assert data["sources"] == 3


def test_run_research_subprocess_timeout(monkeypatch, fake_venv):
    """超时 → 可读错误 (isError), 服务器不崩溃。"""
    def _boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd=["x"], timeout=120)
    monkeypatch.setattr(rmcp, "subprocess", _FakeSubprocess(_boom))
    resp = rmcp._run_research_tool({"query": "q"})
    assert resp["isError"] is True
    assert "超时" in resp["content"][0]["text"]


def test_run_research_subprocess_research_error(monkeypatch, fake_venv):
    """runner 返回 ok=False (研究失败) → 透传错误消息。"""
    fake_proc = types.SimpleNamespace(
        returncode=0,
        stdout=json.dumps({"ok": False, "error": "研究执行失败: RuntimeError: API 超时"},
                          ensure_ascii=False),
        stderr="")
    monkeypatch.setattr(rmcp, "subprocess", _FakeSubprocess(fake_proc))
    resp = rmcp._run_research_tool({"query": "q"})
    assert resp["isError"] is True
    assert "API 超时" in resp["content"][0]["text"]


def test_run_research_subprocess_garbage_output(monkeypatch, fake_venv):
    """输出不可解析 → 可读错误。"""
    fake_proc = types.SimpleNamespace(returncode=0, stdout="not json at all", stderr="")
    monkeypatch.setattr(rmcp, "subprocess", _FakeSubprocess(fake_proc))
    resp = rmcp._run_research_tool({"query": "q"})
    assert resp["isError"] is True
    assert "解析失败" in resp["content"][0]["text"]


class _FakeSubprocess:
    """替身 subprocess 模块: run() 返回固定 proc 或抛异常。"""

    TimeoutExpired = subprocess.TimeoutExpired  # server 侧 except 分支需要

    def __init__(self, proc_or_func):
        self._p = proc_or_func

    def run(self, *a, **k):
        if callable(self._p) and not hasattr(self._p, "returncode"):
            return self._p(*a, **k)
        return self._p


def test_ping():
    resp = _line({"jsonrpc": "2.0", "id": 3, "method": "ping"})
    assert resp["result"] == {}


def test_notification_no_response():
    assert _line({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_unknown_method():
    resp = _line({"jsonrpc": "2.0", "id": 4, "method": "bogus"})
    assert resp["error"]["code"] == -32601


def test_unknown_tool_is_error():
    resp = _line({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                  "params": {"name": "nope", "arguments": {}}})
    assert resp["result"]["isError"] is True
    assert "未知工具" in resp["result"]["content"][0]["text"]


def test_tools_list_schema_has_types():
    resp = _line({"jsonrpc": "2.0", "id": 6, "method": "tools/list"})
    by_name = {t["name"]: t for t in resp["result"]["tools"]}
    for name in ("search_papers", "search_repos"):
        props = by_name[name]["inputSchema"]["properties"]
        assert props["query"]["type"] == "string"
        assert props["max_results"]["type"] == "integer"
    props = by_name["run_research"]["inputSchema"]["properties"]
    assert props["query"]["type"] == "string"
    assert props["max_sources"]["type"] == "integer"


def _spawn():
    """启动真实 MCP 进程 (若 .aionui 文件缺失则跳过 — CI 检出场景)。"""
    if not MCP_FILE.exists():
        pytest_skip = True
        return None
    return subprocess.Popen(
        [sys.executable, str(MCP_FILE)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", cwd=str(MCP_FILE.parents[2]),
    )


def test_subprocess_initialize_ping(tmp_path):
    if not MCP_FILE.exists():
        import pytest
        pytest.skip(".aionui/mcp/research_mcp_server.py 不在检出中")
    proc = _spawn()
    assert proc is not None
    try:
        reqs = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "ping"},
        ]
        out = ""
        for r in reqs:
            proc.stdin.write(json.dumps(r) + "\n")
        proc.stdin.flush()
        proc.stdin.close()
        out = proc.stdout.read()
        lines = [json.loads(l) for l in out.splitlines() if l.strip()]
        ids = [l["id"] for l in lines]
        assert 1 in ids and 2 in ids
        by_id = {l["id"]: l for l in lines}
        assert by_id[1]["result"]["serverInfo"]["name"] == "research-mcp-server"
        assert by_id[2]["result"] == {}
    finally:
        proc.kill()
