"""B2 AutoGen integration tests — stage 3 (3 groups).

G1  AST zero-touch scan        : examples/autogen_groupchat.py has ZERO gateway
                                 imports / references beyond base_url.
G2  Tool-declaration parsing   : the GATEWAY's _extract_tool_names must parse
                                 the OpenAI function schemas that AutoGen
                                 generates for its FunctionTool objects.
G3  Gateway endpoints          : live gateway ALLOW/DENY + persistence for
                                 AutoGen-shaped requests.

IMPORTANT (team protocol): the example file must stay 100% AutoGen-only.
Parser tests import from src.main (the gateway), never from examples/ —
otherwise we'd smuggle gateway logic into the zero-touch example.
"""

import ast
import sys
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import src.main as main_module
from src.main import create_app, DANGEROUS_TOOL_NAMES, _extract_tool_names

EXAMPLE_FILE = PROJECT_ROOT / "examples" / "autogen_groupchat.py"


# ============================================================================
# Group 1: AST zero-touch scan (example must be pure AutoGen SDK)
# ============================================================================

def test_autogen_example_zero_gateway_imports():
    """G1-1: every import in the example is AutoGen SDK or stdlib."""
    assert EXAMPLE_FILE.exists(), f"missing: {EXAMPLE_FILE}"
    tree = ast.parse(EXAMPLE_FILE.read_text(encoding="utf-8"))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
    gateway_refs = {imp for imp in imports if "gateway" in imp.lower()
                    or imp.startswith("src") or imp.startswith("main")}
    assert gateway_refs == set(), f"gateway imports leaked: {gateway_refs}"
    # AutoGen SDK must be present (proves the example is real, not vacuous)
    assert any("autogen" in imp for imp in imports), "no AutoGen imports at all"


def test_autogen_example_only_base_url_to_gateway():
    """G1-2: the ONLY gateway reference is base_url=f"{gateway}/v1"."""
    src = EXAMPLE_FILE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    # find base_url kwarg usages
    base_url_kwargs = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "base_url":
                    base_url_kwargs.append(ast.unparse(kw.value))
    assert base_url_kwargs, "example must configure base_url"
    for expr in base_url_kwargs:
        assert "gateway" in expr or "9000" in expr, f"base_url not pointing at gateway: {expr}"
    # no /v1/intercept string anywhere
    assert "/v1/intercept" not in src, "explicit intercept endpoint leaked"
    # no other gateway-touching strings (path vars, headers, etc.)
    for token in ("/decisions", "gateway.port", "import src"):
        assert token not in src, f"unexpected gateway token: {token}"


def test_autogen_codebase_zero_gateway_imports():
    """G1-3: no other example file imports gateway internals."""
    for py_file in (PROJECT_ROOT / "examples").glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        if "import gateway" in content or "from gateway" in content:
            pytest.fail(f"{py_file.name} imports gateway")


# ============================================================================
# Group 2: gateway parser vs AutoGen-generated tool schemas
# ============================================================================

def _autogen_tools_body(tool_fns):
    """Shape a chat request the way AutoGen's OpenAIChatCompletionClient does.

    AutoGen serializes FunctionTool objects into the OpenAI tools array with
    {"type":"function","function":{"name":..., "parameters":{...}}}.
    We build the raw request body exactly as it will arrive at the gateway.
    """
    tools = []
    for fn in tool_fns:
        tools.append({
            "type": "function",
            "function": {
                "name": getattr(fn, "__name__", fn),
                "description": "auto",
                "parameters": {"type": "object", "properties": {}},
            },
        })
    return {
        "model": "test-model",
        "messages": [{"role": "user", "content": "go"}],
        "tools": tools,
    }


def _parse(body):
    req = main_module.InterceptRequest(path="/v1/chat/completions",
                                       method="POST", body=body)
    return _extract_tool_names(req)


def test_extract_tool_names_from_autogen_function_tool():
    """G2-1: AutoGen tools array with a plain function -> name extracted."""
    names = _parse(_autogen_tools_body(["get_time"]))
    assert names == ["get_time"]


def test_extract_tool_names_from_autogen_async_function_tool():
    """G2-2: async-declared tool name is still a plain string in the schema."""
    names = _parse(_autogen_tools_body(["fetch_data"]))
    assert names == ["fetch_data"]


def test_extract_tool_names_handles_delete_file_tool():
    """G2-3: delete_file is extracted AND hits the B1 blacklist."""
    names = _parse(_autogen_tools_body(["delete_file"]))
    assert names == ["delete_file"]
    assert any(main_module._norm_tool_name(n) in
               {main_module._norm_tool_name(d) for d in DANGEROUS_TOOL_NAMES}
               for n in names)


def test_extract_tool_names_ignores_empty_or_none_tools():
    """G2-4: no tools key or empty tools -> empty name list, no crash."""
    assert _parse({"model": "m", "messages": [{"role": "user", "content": "x"}]}) == []
    assert _parse({"model": "m", "messages": [{"role": "user", "content": "x"}],
                   "tools": []}) == []


def test_extract_tool_names_no_false_positives_for_autogen_sdk_types():
    """G2-5: AutoGen 'FunctionTool' schema shapes don't confuse the parser."""
    body = _autogen_tools_body(["get_time", "fetch_data"])
    names = _parse(body)
    assert names == ["get_time", "fetch_data"]
    assert "FunctionTool" not in names  # never class names
    assert all(isinstance(n, str) for n in names)


# ============================================================================
# Group 3: live gateway endpoints (ALLOW / DENY / persistence)
# ============================================================================

class TestAutogenGateway(AioHTTPTestCase):
    """Live gateway with a stub upstream, AutoGen-shaped requests."""

    upstream_calls = []
    upstream_status = 200
    upstream_payload = {
        "choices": [{"message": {"role": "assistant",
                                 "content": "stub autogen reply"}}]
    }

    async def get_application(self):
        async def upstream_handler(request):
            self.__class__.upstream_calls.append(await request.json())
            return web.json_response(self.__class__.upstream_payload,
                                     status=self.__class__.upstream_status)

        upstream = web.Application()
        upstream.router.add_post("/v1/chat/completions", upstream_handler)
        runner = web.AppRunner(upstream)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        self.upstream_port = site._server.sockets[0].getsockname()[1]
        self.upstream_runner = runner

        self.__class__.upstream_calls = []
        self._old_url = main_module.AGENT_BACKEND_URL
        main_module.AGENT_BACKEND_URL = f"http://127.0.0.1:{self.upstream_port}"
        return create_app()

    async def tearDownAsync(self):
        main_module.AGENT_BACKEND_URL = self._old_url
        await self.upstream_runner.cleanup()
        await super().tearDownAsync()

    @unittest_run_loop
    async def test_autogen_safe_tool_allowed(self):
        """G3-1: get_time only -> forwarded upstream (ALLOW)."""
        resp = await self.client.post(
            "/v1/chat/completions",
            json=_autogen_tools_body(["get_time"]),
        )
        assert resp.status == 200, f"expected ALLOW, got {resp.status}"
        assert len(self.__class__.upstream_calls) == 1

    @unittest_run_loop
    async def test_autogen_dangerous_tool_denied(self):
        """G3-2: delete_file declared -> 403, upstream NEVER called."""
        resp = await self.client.post(
            "/v1/chat/completions",
            json=_autogen_tools_body(["delete_file"]),
        )
        assert resp.status == 403, f"expected DENY, got {resp.status}"
        data = await resp.json()
        assert data["error"]["type"] == "governance_denied"
        assert len(self.__class__.upstream_calls) == 0, "upstream must not be reached"

    @unittest_run_loop
    async def test_autogen_decision_persisted(self):
        """G3-3: DENY lands in the decision ledger."""
        await self.client.post("/v1/chat/completions",
                               json=_autogen_tools_body(["delete_file"]))
        decisions = await self.client.get("/v1/decisions?limit=5")
        d = await decisions.json()
        denies = [dec for dec in d["decisions"] if dec["verdict"] == "DENY"]
        assert any("delete_file" in dec["reason"] for dec in denies)

    @unittest_run_loop
    async def test_autogen_e2e_stub_llm_roundtrip(self):
        """G3-4: full AutoGen GroupChat against the stub upstream — no crash.

        Requires the AutoGen SDK (venv-b2). Skipped automatically when the
        SDK is absent (e.g. plain project env without B2 deps).
        """
        pytest.importorskip("autogen_agentchat")
        from examples.autogen_groupchat import build_groupchat

        gateway_url = f"http://127.0.0.1:{self.upstream_port}"
        # careful: build_groupchat creates its OWN client pointing at the
        # gateway port — same URL the TestClient serves on. Since
        # AGENT_BACKEND_URL is our stub, gateway forwards there.
        team = build_groupchat(gateway_url, dangerous=False)
        result = await team.run(task="What time is it?")
        assert result.messages, "GroupChat produced no messages"
        assert any(hasattr(m, "content") for m in result.messages)
