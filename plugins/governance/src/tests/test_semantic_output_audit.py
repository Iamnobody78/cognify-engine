"""DEBT-0020 tests — output-side semantic async post-check (agent_response).

Symmetric with input-side semantic_hook (TASK-REAL-009):
1. Fail-soft: judge crash / disabled -> None, response flow untouched.
2. Extraction: choices[0].message.content pulled from OpenAI-shaped response;
   non-JSON -> raw text; bounded truncation at AGENT_RESPONSE_MAX_CHARS.
3. Upgrade-only via revoke_registry: high-score ESCALATE revokes the trace
   (subsequent requests short-circuit SUSPEND) — same mechanism as input side.
4. Fired from output paths: chat non-streaming and _proxy_forward
   (streaming uses bounded accumulation; covered by extraction bounds).
"""

import asyncio
import json

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

import src.semantic_hook as sh
import src.main as main_module
from src.revoke import revoke_registry
from src.main import create_app, InterceptRequest
from src.semantic_hook import (extract_agent_response,
                               semantic_output_audit_async,
                               AGENT_RESPONSE_MAX_CHARS)


def _run(coro):
    return asyncio.run(coro)


def _flush_tasks(n=10):
    """Let fire-and-forget tasks run to completion (no real I/O)."""
    async def _f():
        for _ in range(n):
            await asyncio.sleep(0.005)
    _run(_f())


# ── unit: extraction ────────────────────────────────────────────────────────


def test_extract_openai_shaped():
    body = json.dumps({"choices": [{"message": {"role": "assistant", "content": "hi there"}}]})
    assert extract_agent_response(body) == "hi there"


def test_extract_non_json_raw():
    assert extract_agent_response("plain text body") == "plain text body"


def test_extract_empty():
    assert extract_agent_response("") == ""
    assert extract_agent_response(None) == ""


def test_extract_bounded_truncation():
    long = "Y" * (AGENT_RESPONSE_MAX_CHARS * 2)
    out = extract_agent_response(long)
    assert len(out) <= AGENT_RESPONSE_MAX_CHARS
    assert out.startswith("Y" * 100)
    assert "...[truncated]..." in out


def test_extract_missing_choices_falls_back_raw():
    body = json.dumps({"choices": []})
    assert extract_agent_response(body) == body


# ── unit: semantic_output_audit_async (mock judge, real registry) ───────────


def test_output_audit_disabled_returns_none(monkeypatch):
    monkeypatch.setattr(sh, "SEMANTIC_HOOK_ENABLED", False)
    assert _run(semantic_output_audit_async("tr-x", "some output")) is None


def test_output_audit_failsoft_on_judge_crash(monkeypatch):
    monkeypatch.setattr(sh, "SEMANTIC_HOOK_ENABLED", True)

    async def boom(prompt):
        raise RuntimeError("judge down")

    monkeypatch.setattr(sh, "semantic_hook", boom)
    assert _run(semantic_output_audit_async("tr-x", "output")) is None


def test_output_audit_high_score_revokes(monkeypatch):
    monkeypatch.setattr(sh, "SEMANTIC_HOOK_ENABLED", True)

    async def esc(prompt):
        return {"score": 0.97, "flags": ["secrets-leak"], "override": "ESCALATE"}

    monkeypatch.setattr(sh, "semantic_hook", esc)
    revoke_registry.clear()
    _run(semantic_output_audit_async("tr-rev-1", "content"))
    assert revoke_registry.is_revoked("tr-rev-1")
    assert "输出侧语义审计撤销" in revoke_registry.reason_for("tr-rev-1")


def test_output_audit_low_score_no_revoke(monkeypatch):
    monkeypatch.setattr(sh, "SEMANTIC_HOOK_ENABLED", True)

    async def low(prompt):
        return {"score": 0.1, "flags": [], "override": None}

    monkeypatch.setattr(sh, "semantic_hook", low)
    revoke_registry.clear()
    _run(semantic_output_audit_async("tr-low-1", "content"))
    assert not revoke_registry.is_revoked("tr-low-1")


def test_output_audit_empty_content_skips(monkeypatch):
    monkeypatch.setattr(sh, "SEMANTIC_HOOK_ENABLED", True)
    called = {"n": 0}

    async def spy(prompt):
        called["n"] += 1
        return None

    monkeypatch.setattr(sh, "semantic_hook", spy)
    _run(semantic_output_audit_async("tr-empty", ""))
    assert called["n"] == 0  # no judge call for empty content


# ── integration: fired from chat non-streaming forward ──────────────────────


class TestOutputAuditIntegration(AioHTTPTestCase):
    """chat non-streaming forward triggers output audit with trace_id."""

    async def get_application(self):
        async def upstream_handler(request):
            return web.json_response(
                {"choices": [{"message": {"role": "assistant",
                                          "content": "regular answer"}}]}
            )

        upstream = web.Application()
        upstream.router.add_post("/v1/chat/completions", upstream_handler)
        runner = web.AppRunner(upstream)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        self.upstream_port = site._server.sockets[0].getsockname()[1]
        self.upstream_runner = runner

        self._old_url = main_module.AGENT_BACKEND_URL
        main_module.AGENT_BACKEND_URL = f"http://127.0.0.1:{self.upstream_port}"
        self._old_enabled = sh.SEMANTIC_HOOK_ENABLED
        sh.SEMANTIC_HOOK_ENABLED = True

        async def esc(prompt):
            return {"score": 0.95, "flags": ["leak"], "override": "ESCALATE"}

        self._old_hook = sh.semantic_hook
        sh.semantic_hook = esc
        revoke_registry.clear()
        return create_app()

    async def tearDownAsync(self):
        sh.SEMANTIC_HOOK_ENABLED = self._old_enabled
        sh.semantic_hook = self._old_hook
        main_module.AGENT_BACKEND_URL = self._old_url
        await self.upstream_runner.cleanup()
        await super().tearDownAsync()

    @unittest_run_loop
    async def test_chat_nonstreaming_revokes_trace_async(self):
        resp = await self.client.post(
            "/v1/chat/completions",
            json={"model": "m", "messages": [{"role": "user", "content": "hi"}],
                  "stream": False},
        )
        assert resp.status == 200  # response flow untouched (async post-check)
        trace_id = resp.headers.get("X-Trace-ID")
        assert trace_id
        await self._flush()
        assert revoke_registry.is_revoked(trace_id), "output audit must revoke the trace"

    async def _flush(self):
        for _ in range(10):
            await asyncio.sleep(0.005)


class TestProxyForwardOutputAudit(AioHTTPTestCase):
    """_proxy_forward fires output audit when trace_id is passed."""

    async def get_application(self):
        async def upstream_handler(request):
            return web.json_response(
                {"choices": [{"message": {"role": "assistant",
                                          "content": "proxy answer"}}]}
            )

        upstream = web.Application()
        upstream.router.add_post("/v1/chat/completions", upstream_handler)
        runner = web.AppRunner(upstream)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        self.upstream_port = site._server.sockets[0].getsockname()[1]
        self.upstream_runner = runner

        self._old_url = main_module.AGENT_BACKEND_URL
        main_module.AGENT_BACKEND_URL = f"http://127.0.0.1:{self.upstream_port}"
        self._old_enabled = sh.SEMANTIC_HOOK_ENABLED
        sh.SEMANTIC_HOOK_ENABLED = True

        async def esc(prompt):
            return {"score": 0.99, "flags": ["escalation"], "override": "ESCALATE"}

        self._old_hook = sh.semantic_hook
        sh.semantic_hook = esc
        revoke_registry.clear()
        return create_app()

    async def tearDownAsync(self):
        sh.SEMANTIC_HOOK_ENABLED = self._old_enabled
        sh.semantic_hook = self._old_hook
        main_module.AGENT_BACKEND_URL = self._old_url
        await self.upstream_runner.cleanup()
        await super().tearDownAsync()

    @unittest_run_loop
    async def test_proxy_forward_fires_output_audit(self):
        req = InterceptRequest(
            path="/v1/chat/completions",
            method="POST",
            headers={},
            body={"messages": [{"role": "user", "content": "hi"}]},
            agent_id="a1",
        )
        out = await main_module._proxy_forward(req, trace_id="tr-proxy-1")
        assert out is not None
        assert out.get("choices", [{}])[0].get("message", {}).get("content") == "proxy answer"
        await self._flush()
        assert revoke_registry.is_revoked("tr-proxy-1"), "proxy forward must audit output"

    async def _flush(self):
        for _ in range(10):
            await asyncio.sleep(0.005)
