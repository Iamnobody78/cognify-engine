"""LLM-Judge service tests — regression for the stage-A --model sync fix.

Propositions:
1. /v1/health reports the effective JUDGE_MODEL module global (the CLI
   --model fix must keep handlers and health in sync).
2. /v1/judge responds 400 on missing user_prompt and defers to Ollama
   (mocked) — response shape {score, level, flags, model, latency_ms}.
3. fail-soft: Ollama down -> 503 JSON error, service stays alive.
"""

import json

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

import judge.llm_judge as j


class TestJudgeService(AioHTTPTestCase):

    async def get_application(self):
        self._old_model = j.JUDGE_MODEL
        j.JUDGE_MODEL = "qwen2.5:7b"
        return j.create_app()

    async def tearDownAsync(self):
        j.JUDGE_MODEL = self._old_model
        await super().tearDownAsync()

    @unittest_run_loop
    async def test_health_reports_effective_model(self):
        resp = await self.client.get("/v1/health")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
        assert data["model"] == "qwen2.5:7b"  # module global, not stale default

    @unittest_run_loop
    async def test_judge_missing_prompt_422(self):
        resp = await self.client.post("/v1/judge", json={"nope": 1})
        assert resp.status == 422

    @unittest_run_loop
    async def test_judge_ollama_down_failsoft_503(self):
        # call_ollama never raises: it catches and returns None -> 503 JSON
        async def down(session, user_prompt):
            return None

        old = j.call_ollama
        j.call_ollama = down
        try:
            resp = await self.client.post(
                "/v1/judge", json={"user_prompt": "hello"}
            )
            assert resp.status == 503
            data = await resp.json()
            assert "error" in data
        finally:
            j.call_ollama = old

    @unittest_run_loop
    async def test_judge_success_shape(self):
        async def fake_ollama(session, user_prompt):
            assert user_prompt == "normal request"  # handler passes through raw prompt
            return {"score": 0.2, "level": "NORMAL", "flags": []}

        old = j.call_ollama
        j.call_ollama = fake_ollama
        try:
            resp = await self.client.post(
                "/v1/judge", json={"user_prompt": "normal request"}
            )
            assert resp.status == 200
            data = await resp.json()
            assert data["score"] == 0.2
            assert data["level"] == "NORMAL"
            assert data["model"] == "qwen2.5:7b"
            assert data["latency_ms"] >= 0
        finally:
            j.call_ollama = old
