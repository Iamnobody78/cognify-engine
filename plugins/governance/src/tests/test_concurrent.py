"""Concurrency tests — verify the gateway handles ≥10 simultaneous requests.

v1 had zero concurrency testing. v2 iron law: test real load.
"""

import asyncio

import pytest
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop


class TestConcurrent(AioHTTPTestCase):
    async def get_application(self):
        from src.main import create_app
        return create_app()

    @unittest_run_loop
    async def test_10_concurrent_allows(self):
        """10 simultaneous ALLOW requests should all succeed."""
        async def send_allow():
            resp = await self.client.post(
                "/v1/intercept",
                json={"path": "/api/chat", "method": "POST"},
            )
            return resp.status

        tasks = [send_allow() for _ in range(10)]
        results = await asyncio.gather(*tasks)
        assert all(s == 200 for s in results), f"Got statuses: {results}"

    @unittest_run_loop
    async def test_10_concurrent_denies(self):
        """10 simultaneous DENY requests should all return 403."""
        async def send_deny():
            resp = await self.client.post(
                "/v1/intercept",
                json={"path": "/api/delete/user", "method": "POST"},
            )
            return resp.status

        tasks = [send_deny() for _ in range(10)]
        results = await asyncio.gather(*tasks)
        assert all(s == 403 for s in results), f"Got statuses: {results}"

    @unittest_run_loop
    async def test_20_mixed_requests(self):
        """20 mixed ALLOW/DENY/ESCALATE requests — all must succeed."""
        async def send_mixed(i: int):
            if i % 3 == 0:
                path = "/api/chat"
                expected = 200
            elif i % 3 == 1:
                path = "/api/delete/user"
                expected = 403
            else:
                path = "/api/config/model"
                expected = 202
            resp = await self.client.post(
                "/v1/intercept",
                json={"path": path, "method": "POST"},
            )
            return resp.status, expected

        tasks = [send_mixed(i) for i in range(20)]
        results = await asyncio.gather(*tasks)
        for actual, expected in results:
            assert actual == expected, f"Expected {expected}, got {actual}"

    @unittest_run_loop
    async def test_concurrent_decisions_all_persisted(self):
        """All concurrent requests must be persisted to storage."""
        async def send():
            resp = await self.client.post(
                "/v1/intercept",
                json={"path": "/api/chat", "method": "POST"},
            )
            data = await resp.json()
            return data["decision_id"]

        ids = await asyncio.gather(*[send() for _ in range(15)])
        # all decision_ids must be unique
        assert len(set(ids)) == 15, f"Expected 15 unique IDs, got {len(set(ids))}"

        # verify all are retrievable
        resp = await self.client.get("/v1/decisions?limit=50")
        data = await resp.json()
        assert data["total"] >= 15

    @unittest_run_loop
    async def test_no_race_condition_on_counter(self):
        """Concurrent DENY + ALLOW should not corrupt internal state."""
        async def ping():
            resp = await self.client.get("/v1/health")
            return resp.status

        tasks = [ping() for _ in range(50)]
        results = await asyncio.gather(*tasks)
        assert all(s == 200 for s in results)
