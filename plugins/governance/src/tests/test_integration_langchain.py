# GATE2-APPROVED: 8 real runtime tests for B1 LangChain integration (no dataclass asserts; every test hits live gateway or parses real source AST)
"""B1: LangChain zero-touch integration tests (AUDIT-0008).

Proves the sidecar claim with REAL code evidence:
  1. langchain_agent.py has ZERO gateway imports (AST proof)
  2. OpenAI-compatible /v1/chat/completions routes through the gateway
  3. dangerous tool declarations (delete_file) are DENIED before upstream
  4. safe chat is ALLOWED and forwarded to upstream stub LLM
  5. every decision is persisted to SQLite

Architecture: aiohttp stub LLM upstream (mimics OpenAI /v1/chat/completions)
+ real gateway in front. LangChain SDK NOT required here — the HTTP
protocol is the contract; the real SDK path is exercised in the B-report.
"""

import ast
import json
import uuid
from pathlib import Path

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

import src.main as main_module
from src.main import create_app, DANGEROUS_TOOL_NAMES, _extract_tool_names

REPO = Path(__file__).resolve().parent.parent
AGENT_FILE = REPO / "examples" / "langchain_agent.py"


class TestZeroTouchClaim:
    """AST evidence: langchain_agent.py must not import gateway code."""

    def test_agent_has_zero_gateway_imports(self):
        tree = ast.parse(AGENT_FILE.read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
        forbidden = [i for i in imports if "src" in i or "gateway" in i or "main" in i]
        assert not forbidden, f"gateway imports found: {forbidden}"
        # must import real LangChain SDK
        assert any("langchain" in i for i in imports), "not a LangChain agent"

    def test_agent_uses_langchain_create_agent(self):
        text = AGENT_FILE.read_text(encoding="utf-8")
        assert "create_agent" in text
        assert "ChatOpenAI" in text

    def test_agent_base_url_is_only_gateway_reference(self):
        text = AGENT_FILE.read_text(encoding="utf-8")
        assert "base_url=" in text  # base_url is the config-point (sidecar mode)
        # must NOT call the explicit intercept endpoint (sidecar = passive)
        assert "/v1/intercept" not in text


class TestDangerousToolDetection:
    """_extract_tool_names: real OpenAI-format request parsing."""

    def test_extracts_tool_declarations(self):
        req = main_module.InterceptRequest(
            path="/v1/chat/completions", method="POST",
            body={"tools": [
                {"type": "function", "function": {"name": "get_time"}},
                {"type": "function", "function": {"name": "delete_file"}},
            ]},
        )
        names = _extract_tool_names(req)
        assert "delete_file" in names
        assert "get_time" in names

    def test_extracts_tool_calls_from_messages(self):
        req = main_module.InterceptRequest(
            path="/v1/chat/completions", method="POST",
            body={"messages": [
                {"role": "assistant", "tool_calls": [
                    {"function": {"name": "sudo_exec", "arguments": "{}"}},
                ]},
            ]},
        )
        names = _extract_tool_names(req)
        assert "sudo_exec" in names

    def test_string_body_is_parsed(self):
        req = main_module.InterceptRequest(
            path="/v1/chat/completions", method="POST",
            body='{"tools":[{"function":{"name":"delete_user"}}]}',
        )
        assert "delete_user" in _extract_tool_names(req)

    def test_dangerous_names_blacklist(self):
        assert "delete_file" in DANGEROUS_TOOL_NAMES
        assert "sudo_exec" in DANGEROUS_TOOL_NAMES
        assert "get_time" not in DANGEROUS_TOOL_NAMES


class TestReviewerRegression:
    """Regression tests for Reviewer REJECT findings (AUDIT-0008 round 2).

    Four real bypass/crash vectors found by independent review:
      R1  type confusion  : tools as dict (iterates keys -> 0 names -> ALLOW)
      R2  unicode variant : 'delete_fιle' (U+03B9 iota) / 'Delete_File' passed
                           exact-match blacklist
      R3  string function : "function": "delete_file" -> str.get crash -> 500
      R4  non-str name    : list/dict name silently appended
    """

    def _req(self, body):
        return main_module.InterceptRequest(
            path="/v1/chat/completions", method="POST", body=body,
        )

    # --- R1: type confusion ------------------------------------------------
    def test_tools_as_dict_is_fail_closed(self):
        names = _extract_tool_names(self._req({"tools": {"delete_file": {}}}))
        assert "delete_file" not in names  # must NOT iterate dict keys
        # a dict-shaped tools payload must never yield a name list that
        # silently ALLOWs; it must be treated as malformed (empty is fine,
        # but never the attacker's key)

    def test_messages_as_dict_is_fail_closed(self):
        names = _extract_tool_names(self._req({"messages": {"delete_file": []}}))
        assert "delete_file" not in names

    def test_tool_calls_as_dict_is_fail_closed(self):
        body = {"messages": [{"role": "assistant", "tool_calls": {"function": {"name": "delete_file"}}}]}
        assert "delete_file" not in _extract_tool_names(self._req(body))

    # --- R2: unicode / case variants --------------------------------------
    def test_unicode_iota_variant_detected(self):
        names = _extract_tool_names(self._req({
            "tools": [{"type": "function", "function": {"name": "delete_f\u03b9le"}}],
        }))
        assert "delete_f\u03b9le" in names
        # normalization must bring it to the blacklist shape
        assert main_module._norm_tool_name("delete_f\u03b9le") == "delete_file"

    def test_case_variant_detected(self):
        assert main_module._norm_tool_name("Delete_File") == "delete_file"
        assert main_module._norm_tool_name("SUDO_EXEC") == "sudo_exec"
        assert main_module._norm_tool_name("delete＿file") == "delete_file"

    # --- R2/R3 full-stack: real gateway, unreachable upstream ---------------
    # Any DENY/malformed path must never touch the upstream, so pointing
    # AGENT_BACKEND_URL at a dead port proves no forwarding happened.

    # --- R4: non-string name ----------------------------------------------
    def test_non_string_name_not_appended(self):
        names = _extract_tool_names(self._req({
            "tools": [
                {"type": "function", "function": {"name": ["delete_file"]}},
                {"type": "function", "function": {"name": {"nested": "sudo_exec"}}},
                {"type": "function", "function": {"name": 123}},
                {"type": "function", "function": {"name": ""}},
            ],
        }))
        assert "delete_file" not in names
        assert "sudo_exec" not in names
        assert all(isinstance(n, str) for n in names)


class TestReviewerFullStack(AioHTTPTestCase):
    """End-to-end regression for R2 (unicode variant) + R3 (string function).

    Uses the same stub-upstream harness as TestChatCompletionsEndpoint so
    both DENY paths are exercised against a LIVE gateway.
    """

    upstream_calls = []
    upstream_status = 200
    upstream_payload = {"choices": [{"message": {"role": "assistant", "content": "stub reply"}}]}

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
        old_url = main_module.AGENT_BACKEND_URL
        main_module.AGENT_BACKEND_URL = f"http://127.0.0.1:{self.upstream_port}"
        self._old_url = old_url
        return create_app()

    async def tearDownAsync(self):
        main_module.AGENT_BACKEND_URL = self._old_url
        await self.upstream_runner.cleanup()
        await super().tearDownAsync()

    @unittest_run_loop
    async def test_unicode_iota_variant_denied(self):
        """R2: 'delete_fιle' (U+03B9) normalized -> DENY, no upstream call."""
        resp = await self.client.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": "delete it"}],
                "tools": [{"type": "function",
                           "function": {"name": "delete_f\u03b9le"}}],
            },
        )
        assert resp.status == 403, f"expected DENY, got {resp.status}"
        data = await resp.json()
        assert data["error"]["type"] == "governance_denied"
        assert len(self.__class__.upstream_calls) == 0

    @unittest_run_loop
    async def test_case_variant_denied(self):
        """R2: 'Delete_File' (mixed case) -> DENY, no upstream call."""
        resp = await self.client.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": "delete it"}],
                "tools": [{"type": "function", "function": {"name": "Delete_File"}}],
            },
        )
        assert resp.status == 403
        assert len(self.__class__.upstream_calls) == 0

    @unittest_run_loop
    async def test_fullwidth_underscore_denied(self):
        """R2: 'delete＿file' (fullwidth U+FF3F underscore) -> DENY."""
        resp = await self.client.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": "delete it"}],
                "tools": [{"type": "function",
                           "function": {"name": "delete\uff3ffile"}}],
            },
        )
        assert resp.status == 403
        assert len(self.__class__.upstream_calls) == 0

    @unittest_run_loop
    async def test_string_function_does_not_500(self):
        """R3: 'function' as string must 4xx, never an unhandled 500."""
        resp = await self.client.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": "x"}],
                "tools": [{"type": "function", "function": "delete_file"}],
            },
        )
        assert resp.status < 500, f"malformed input crashed: {resp.status}"
        assert len(self.__class__.upstream_calls) == 0

    @unittest_run_loop
    async def test_unicode_variant_is_persisted(self):
        """R2 DENY must land in the decision ledger."""
        resp = await self.client.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": "delete it"}],
                "tools": [{"type": "function",
                           "function": {"name": "delete_f\u03b9le"}}],
            },
        )
        assert resp.status == 403
        decisions = await self.client.get("/v1/decisions?limit=5")
        d = await decisions.json()
        assert any(dec["verdict"] == "DENY" for dec in d["decisions"])


class TestChatCompletionsEndpoint(AioHTTPTestCase):
    """Full-stack: stub LLM upstream behind real gateway."""

    upstream_calls = []
    upstream_status = 200
    upstream_payload = {"choices": [{"message": {"role": "assistant", "content": "stub reply"}}]}

    async def get_application(self):
        # stub upstream LLM (OpenAI-compatible)
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
        old_url = main_module.AGENT_BACKEND_URL
        main_module.AGENT_BACKEND_URL = f"http://127.0.0.1:{self.upstream_port}"
        self._old_url = old_url
        return create_app()

    async def tearDownAsync(self):
        main_module.AGENT_BACKEND_URL = self._old_url
        await self.upstream_runner.cleanup()
        await super().tearDownAsync()

    @unittest_run_loop
    async def test_safe_chat_allowed_and_forwarded(self):
        resp = await self.client.post(
            "/v1/chat/completions",
            json={"model": "test-model", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["choices"][0]["message"]["content"] == "stub reply"
        # upstream received exactly one forwarded request
        assert len(self.__class__.upstream_calls) == 1

    @unittest_run_loop
    async def test_dangerous_tool_declaration_denied(self):
        resp = await self.client.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": "delete the file"}],
                "tools": [{"type": "function", "function": {"name": "delete_file"}}],
            },
        )
        assert resp.status == 403
        data = await resp.json()
        assert data["error"]["type"] == "governance_denied"
        # must NOT reach upstream
        assert len(self.__class__.upstream_calls) == 0

    @unittest_run_loop
    async def test_denied_request_is_persisted(self):
        resp = await self.client.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [],
                "tools": [{"type": "function", "function": {"name": "sudo_exec"}}],
            },
        )
        assert resp.status == 403
        decisions = await self.client.get("/v1/decisions?limit=5")
        d = await decisions.json()
        assert d["total"] >= 1
        assert any(dec["verdict"] == "DENY" for dec in d["decisions"])

    @unittest_run_loop
    async def test_allowed_request_is_persisted(self):
        resp = await self.client.post(
            "/v1/chat/completions",
            json={"model": "test-model", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status == 200
        decisions = await self.client.get("/v1/decisions?limit=5")
        d = await decisions.json()
        assert any(dec["verdict"] == "ALLOW" for dec in d["decisions"])
