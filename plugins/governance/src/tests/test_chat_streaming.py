"""DEBT-0004: streaming pass-through tests for /v1/chat/completions.

Proves the gateway forwards SSE responses chunk-by-chunk when the client
requests stream:true, while the non-streaming path keeps the buffered JSON
behavior (no regression). Stub upstream emits SSE events only when asked.
"""

import json

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

import src.main as main_module
from src.main import create_app

SSE_BODY = (
    "data: {\"id\":\"1\",\"choices\":[{\"delta\":{\"content\":\"Hello \"}}]}\n\n"
    "data: {\"id\":\"1\",\"choices\":[{\"delta\":{\"content\":\"world\"}}]}\n\n"
    "data: {\"id\":\"1\",\"choices\":[{\"delta\":{\"content\":\"!\"}}]}\n\n"
    "data: [DONE]\n\n"
)


class TestChatStreaming(AioHTTPTestCase):
    """Full-stack: stub LLM upstream emits SSE; gateway must pass through."""

    upstream_calls = []

    async def get_application(self):
        async def upstream_handler(request):
            req_body = await request.json()
            self.__class__.upstream_calls.append(req_body)
            if req_body.get("stream"):
                return web.Response(
                    text=SSE_BODY,
                    headers={"Content-Type": "text/event-stream"},
                )
            return web.json_response(
                {"choices": [{"message": {"role": "assistant", "content": "stub reply"}}]}
            )

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
    async def test_stream_true_passes_through_sse(self):
        resp = await self.client.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        )
        assert resp.status == 200
        ct = resp.headers.get("Content-Type", "")
        assert ct.startswith("text/event-stream"), f"CT={ct!r}"
        body = await resp.text()
        assert body == SSE_BODY, f"streamed body mismatch: {body!r}"
        assert len(self.__class__.upstream_calls) == 1

    @unittest_run_loop
    async def test_stream_false_keeps_buffered_json(self):
        resp = await self.client.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
            },
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["choices"][0]["message"]["content"] == "stub reply"
        assert len(self.__class__.upstream_calls) == 1

    @unittest_run_loop
    async def test_stream_default_matches_non_stream(self):
        resp = await self.client.post(
            "/v1/chat/completions",
            json={"model": "test-model", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["choices"][0]["message"]["content"] == "stub reply"

    @unittest_run_loop
    async def test_dangerous_tool_still_denied_on_stream_request(self):
        resp = await self.client.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": "delete the file"}],
                "tools": [{"type": "function", "function": {"name": "delete_file"}}],
                "stream": True,
            },
        )
        assert resp.status == 403
        data = await resp.json()
        assert data["error"]["type"] == "governance_denied"
        assert len(self.__class__.upstream_calls) == 0

    @unittest_run_loop
    async def test_upstream_unreachable_returns_502(self):
        old = main_module.AGENT_BACKEND_URL
        main_module.AGENT_BACKEND_URL = "http://127.0.0.1:1"  # dead port
        try:
            resp = await self.client.post(
                "/v1/chat/completions",
                json={
                    "model": "m",
                    "messages": [{"role": "user", "content": "x"}],
                    "stream": True,
                },
            )
            assert resp.status == 502, f"expected 502, got {resp.status}"
        finally:
            main_module.AGENT_BACKEND_URL = old

    @unittest_run_loop
    async def test_stream_chunks_forwarded_in_order(self):
        # Critique R1 5.1: chunk ORDER must be verified, not just byte-exact body.
        # Upstream emits 4 streamed chunks with order-sensitive payloads; the
        # gateway must relay them in EXACT sequence (1,2,3,4).
        import asyncio

        async def chunked_upstream(request):
            resp = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
            await resp.prepare(request)
            for i in range(1, 5):
                await resp.write(f"data: chunk-{i}\n\n".encode("utf-8"))
                await asyncio.sleep(0.01)
            await resp.write_eof()
            return resp

        upstream = web.Application()
        upstream.router.add_post("/v1/chat/completions", chunked_upstream)
        runner = web.AppRunner(upstream)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]

        old = main_module.AGENT_BACKEND_URL
        main_module.AGENT_BACKEND_URL = f"http://127.0.0.1:{port}"
        try:
            resp = await self.client.post(
                "/v1/chat/completions",
                json={
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "order test"}],
                    "stream": True,
                },
            )
            assert resp.status == 200
            body = await resp.text()
            # order-sensitive: chunk-1..chunk-4 must appear in exact sequence
            idx = [body.find(f"chunk-{i}") for i in (1, 2, 3, 4)]
            assert all(i >= 0 for i in idx), f"missing chunks: {idx}"
            assert idx == sorted(idx), f"chunks out of order: {idx}"
        finally:
            main_module.AGENT_BACKEND_URL = old
            await runner.cleanup()


if __name__ == "__main__":
    import unittest

    unittest.main()
