"""DEBT-0018: gateway-level request/response body size limits.

Contract:
- Request side (fail-closed): /v1/intercept and /v1/chat/completions reject
  oversize bodies with 413 + a DENY decision persisted (matched_rule=
  "body-too-large"), covering both the content-length fast path and the
  controlled-read fallback for chunked (no-length) bodies.
- Response side (truncate, never reject): upstream payloads over the limit
  are truncated on both _proxy_forward and the non-streaming chat path.
- Limits are env-overridable (GOV_MAX_BODY_BYTES / GOV_MAX_RESP_BYTES).
"""

import json
import os

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

import src.main as main_module
from src.main import create_app, InterceptRequest

_BIG_CONTENT = "x" * 2048  # > 1024 test limit


def _big_intercept_payload() -> dict:
    return {
        "agent_id": "a1",
        "path": "/v1/chat/completions",
        "method": "POST",
        "headers": {},
        "body": {"messages": [{"role": "user", "content": _BIG_CONTENT}]},
    }


class TestRequestBodyLimits(AioHTTPTestCase):
    """Request side: oversize -> 413 + DENY persisted (fail-closed)."""

    async def get_application(self):
        self._old_max_body = main_module._max_body_bytes
        main_module._max_body_bytes = lambda: 1024  # shrink limit for tests
        return create_app()

    async def tearDownAsync(self):
        main_module._max_body_bytes = self._old_max_body
        await super().tearDownAsync()

    @unittest_run_loop
    async def test_intercept_oversize_rejected_413_and_persisted(self):
        resp = await self.client.post("/v1/intercept", json=_big_intercept_payload())
        assert resp.status == 413, f"status={resp.status}"
        data = await resp.json()
        # 解析前拒绝 → error 契约 (与 malformed-400 同源 _deny_decision)
        assert data["error"]["type"] == "governance_denied"
        assert data["error"]["decision_id"]
        # auditable: the oversize rejection must be on the decision chain
        recent = main_module.storage.get_recent(limit=10)
        assert any(
            d.get("matched_rule") == "body-too-large" for d in recent
        ), "oversize rejection must be persisted"

    @unittest_run_loop
    async def test_intercept_small_body_unaffected(self):
        resp = await self.client.post(
            "/v1/intercept", json={"path": "/api/unknown", "method": "GET"}
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["verdict"] == "ALLOW"

    @unittest_run_loop
    async def test_chat_oversize_content_length_fast_path_413(self):
        resp = await self.client.post(
            "/v1/chat/completions",
            json={"model": "m", "messages": [{"role": "user", "content": _BIG_CONTENT}]},
        )
        assert resp.status == 413, f"status={resp.status}"
        data = await resp.json()
        assert data["error"]["type"] == "governance_denied"
        assert data["error"]["decision_id"]

    @unittest_run_loop
    async def test_chat_oversize_chunked_fallback_413(self):
        # chunked request -> no content-length -> controlled-read fallback
        async def gen():
            yield json.dumps(
                {"model": "m", "messages": [{"role": "user", "content": _BIG_CONTENT}]}
            ).encode()

        resp = await self.client.post(
            "/v1/chat/completions",
            data=gen(),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 413, f"status={resp.status}"
        data = await resp.json()
        assert data["error"]["type"] == "governance_denied"

    @unittest_run_loop
    async def test_chat_small_body_still_reaches_upstream(self):
        resp = await self.client.post(
            "/v1/chat/completions",
            json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
        )
        # no upstream stub in this class -> non-proxy path still must respond
        # (policy verdict path; 200 means the limit did not wrongly reject)
        assert resp.status in (200, 502), f"status={resp.status}"


class TestEnvOverrides:
    """Limit functions must honor GOV_* env overrides and sane defaults."""

    def test_max_body_bytes_default(self):
        old = os.environ.pop("GOV_MAX_BODY_BYTES", None)
        try:
            assert main_module._max_body_bytes() == 10 * 1024 * 1024
        finally:
            if old is not None:
                os.environ["GOV_MAX_BODY_BYTES"] = old

    def test_max_body_bytes_env_override(self):
        old = os.environ.get("GOV_MAX_BODY_BYTES")
        os.environ["GOV_MAX_BODY_BYTES"] = "2048"
        try:
            assert main_module._max_body_bytes() == 2048
        finally:
            if old is None:
                os.environ.pop("GOV_MAX_BODY_BYTES", None)
            else:
                os.environ["GOV_MAX_BODY_BYTES"] = old

    def test_max_resp_bytes_default(self):
        old = os.environ.pop("GOV_MAX_RESP_BYTES", None)
        try:
            assert main_module._max_resp_bytes() == 10 * 1024 * 1024
        finally:
            if old is not None:
                os.environ["GOV_MAX_RESP_BYTES"] = old


class TestResponseTruncation(AioHTTPTestCase):
    """Response side: oversized upstream payloads are truncated, never rejected."""

    async def get_application(self):
        async def upstream_handler(request):
            req_body = await request.json()
            if req_body.get("_big"):
                return web.json_response({"data": "y" * 2000})
            return web.json_response(
                {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
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
        self._old_resp = main_module._max_resp_bytes
        main_module._max_resp_bytes = lambda: 512  # shrink for tests
        self._old_body = main_module._max_body_bytes
        main_module._max_body_bytes = lambda: 1024
        return create_app()

    async def tearDownAsync(self):
        main_module.AGENT_BACKEND_URL = self._old_url
        main_module._max_resp_bytes = self._old_resp
        main_module._max_body_bytes = self._old_body
        await self.upstream_runner.cleanup()
        await super().tearDownAsync()

    @unittest_run_loop
    async def test_chat_nonstreaming_oversize_response_truncated(self):
        resp = await self.client.post(
            "/v1/chat/completions",
            json={
                "model": "m",
                "messages": [{"role": "user", "content": "hi"}],
                "_big": True,
                "stream": False,
            },
        )
        assert resp.status == 200, "oversize upstream response must never be rejected"
        text = await resp.text()
        assert len(text) <= 512, f"truncated body too big: {len(text)} bytes"

    @unittest_run_loop
    async def test_proxy_forward_oversize_response_truncated(self):
        req = InterceptRequest(
            path="/v1/chat/completions",
            method="POST",
            headers={},
            body={"messages": [{"role": "user", "content": "hi"}], "_big": True},
            agent_id="a1",
        )
        out = await main_module._proxy_forward(req)
        assert out is not None
        assert out.get("truncated") is True, "oversize upstream must be flagged truncated"
        assert out["status"] == 200
        assert len(out.get("body", "")) <= 1000
