"""B3: hybrid-mode validation — one gateway, B1+B2 style clients.

Core proposition: a single gateway concurrently serving LangChain-style
(B1) and AutoGen-style (B2) OpenAI-compatible clients must apply IDENTICAL
governance verdicts, keep routing isolated, and attribute decisions per
client (x-agent-id). HTTP protocol is the contract (no SDK required).
"""

import json
import uuid

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

import src.main as main_module
from src.main import create_app, DANGEROUS_TOOL_NAMES


class TestB3HybridMode(AioHTTPTestCase):
    """Concurrent B1+B2 clients against one gateway + one stub upstream."""

    upstream_calls = []

    async def get_application(self):
        async def upstream_handler(request):
            req_body = await request.json()
            agent_id = request.headers.get("x-agent-id", "unknown")
            self.__class__.upstream_calls.append({"agent_id": agent_id, "body": req_body})
            if req_body.get("stream"):
                return web.Response(
                    text=(
                        "data: {\"choices\":[{\"delta\":{\"content\":\"B3 \"}}]}\n\n"
                        "data: {\"choices\":[{\"delta\":{\"content\":\"ok\"}}]}\n\n"
                        "data: [DONE]\n\n"
                    ),
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

    def _chat_body(self, agent_id, content="hello", stream=False, tools=None):
        body = {
            "model": "test-model",
            "messages": [{"role": "user", "content": content}],
            "stream": stream,
        }
        if tools:
            body["tools"] = tools
        return body, {"x-agent-id": agent_id}

    @unittest_run_loop
    async def test_b1_and_b2_concurrent_safe_chat(self):
        # V1a: B1 (LangChain-style) + B2 (AutoGen-style) concurrently, both safe
        import asyncio

        body_b1, hdr_b1 = self._chat_body("b1-langchain")
        body_b2, hdr_b2 = self._chat_body("b2-autogen")
        r1, r2 = await asyncio.gather(
            self.client.post("/v1/chat/completions", json=body_b1, headers=hdr_b1),
            self.client.post("/v1/chat/completions", json=body_b2, headers=hdr_b2),
        )
        assert r1.status == 200 and r2.status == 200
        assert (await r1.json())["choices"][0]["message"]["content"] == "stub reply"
        assert (await r2.json())["choices"][0]["message"]["content"] == "stub reply"

    @unittest_run_loop
    async def test_dangerous_tool_denied_for_both_clients(self):
        # V1b: dangerous tool -> 403 for BOTH frameworks, upstream untouched
        dangerous = [{"type": "function", "function": {"name": "delete_file"}}]
        body_b1, hdr_b1 = self._chat_body("b1-langchain", content="remove it", tools=dangerous)
        body_b2, hdr_b2 = self._chat_body("b2-autogen", content="remove it", tools=dangerous)
        r1 = await self.client.post("/v1/chat/completions", json=body_b1, headers=hdr_b1)
        r2 = await self.client.post("/v1/chat/completions", json=body_b2, headers=hdr_b2)
        assert r1.status == 403 and r2.status == 403
        assert len(self.__class__.upstream_calls) == 0, "dangerous must not reach upstream"

    @unittest_run_loop
    async def test_agent_attribution_isolated(self):
        # V3: x-agent-id reaches upstream — decisions attributable per client
        body_b1, hdr_b1 = self._chat_body("b1-langchain")
        body_b2, hdr_b2 = self._chat_body("b2-autogen")
        await self.client.post("/v1/chat/completions", json=body_b1, headers=hdr_b1)
        await self.client.post("/v1/chat/completions", json=body_b2, headers=hdr_b2)
        agent_ids = sorted(c["agent_id"] for c in self.__class__.upstream_calls)
        assert agent_ids == ["b1-langchain", "b2-autogen"], agent_ids

    @unittest_run_loop
    async def test_stream_true_works_for_b2_style(self):
        # V2: SSE streaming across framework — AutoGen style with stream:true
        body, hdr = self._chat_body("b2-autogen", content="stream me", stream=True)
        resp = await self.client.post("/v1/chat/completions", json=body, headers=hdr)
        assert resp.status == 200
        ct = resp.headers.get("Content-Type", "")
        assert ct.startswith("text/event-stream"), f"CT={ct!r}"
        text = await resp.text()
        assert "data: [DONE]" in text, text
        # SSE passthrough keeps delta chunks as separate events — reconstruct
        # the streamed content to verify both chunks were delivered in order.
        chunks = [
            json.loads(line[6:])["choices"][0]["delta"]["content"]
            for line in text.splitlines()
            if line.startswith("data: ") and line.strip() != "data: [DONE]"
        ]
        assert "".join(chunks) == "B3 ok", text

    @unittest_run_loop
    async def test_state_isolated_between_clients(self):
        # V3b: one client's dangerous call must not affect the other's next safe call
        dangerous = [{"type": "function", "function": {"name": "delete_file"}}]
        body_b2, hdr_b2 = self._chat_body("b2-autogen", content="remove", tools=dangerous)
        r_deny = await self.client.post("/v1/chat/completions", json=body_b2, headers=hdr_b2)
        assert r_deny.status == 403
        # B1 still works fine afterwards
        body_b1, hdr_b1 = self._chat_body("b1-langchain")
        r_ok = await self.client.post("/v1/chat/completions", json=body_b1, headers=hdr_b1)
        assert r_ok.status == 200
        assert len(self.__class__.upstream_calls) == 1, "only the safe B1 call reaches upstream"


if __name__ == "__main__":
    import unittest

    unittest.main()
