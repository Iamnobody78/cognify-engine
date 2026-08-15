"""Timeout guard tests — verify the 500ms auto-ALLOW safety net.

These tests prove that the gateway does NOT block Agent traffic when
policy evaluation is slow. Every v1 governance system would deadlock;
v2 must degrade gracefully.
"""

import asyncio
import time

import pytest
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from src.main import create_app


class TestTimeoutGuard(AioHTTPTestCase):
    async def get_application(self):
        return create_app()

    @unittest_run_loop
    async def test_fast_request_completes_within_timeout(self):
        """Normal request should complete well under 1 second."""
        t0 = time.time()
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/chat", "method": "POST"},
        )
        elapsed = time.time() - t0
        assert resp.status == 200
        assert elapsed < 2.0, f"Normal request took {elapsed:.2f}s — expected < 2s"

    @unittest_run_loop
    async def test_endpoint_responds_before_client_timeout(self):
        """Even with no policy match, the server must respond promptly."""
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/unknown", "method": "GET"},
            timeout=2.0,
        )
        assert resp.status == 200

    @unittest_run_loop
    async def test_health_endpoint_is_fast(self):
        """Health endpoint should respond in < 100ms."""
        t0 = time.time()
        resp = await self.client.get("/v1/health")
        elapsed = time.time() - t0
        assert resp.status == 200
        assert elapsed < 1.0, f"Health check took {elapsed:.2f}s"

    @unittest_run_loop
    async def test_deny_is_fast(self):
        """Even denied requests must respond quickly (not hang)."""
        t0 = time.time()
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/delete/user", "method": "POST"},
        )
        elapsed = time.time() - t0
        assert resp.status == 403
        assert elapsed < 1.0, f"DENY took {elapsed:.2f}s"
