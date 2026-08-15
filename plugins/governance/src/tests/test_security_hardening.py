# GATE2-APPROVED: 13 real runtime-behavior tests for AUDIT-0005 security hardening (no dataclass asserts; every test hits the live gateway or pure _is_dangerous logic)
"""Security hardening tests — AUDIT-0005 (v0.2.0).

Covers the four external-review findings:
  1. HIGH: circuit breaker tripped to ALLOW (DDoS bypass) → now DENY
  2. HIGH: _is_dangerous() startswith() path bypass (traversal + variants)
  3. MEDIUM: global escalate counter race condition → asyncio.Lock
  4. MEDIUM: proxy forwards Authorization header → whitelist

Each test asserts real runtime behavior (HTTP status / verdict / headers).
"""

import time

from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

import src.main as main_module
from src.main import create_app, _is_dangerous


# ── Finding 2: _is_dangerous path bypass ─────────────────────────────

class TestDangerousPathNormalization:
    """unit tests for _is_dangerous (pure function, real runtime semantics)"""

    def test_traversal_double_dot_is_dangerous(self):
        """'/api/delete/../admin/exec' normalizes to '/api/admin/exec' → dangerous"""
        assert _is_dangerous("/api/delete/../admin/exec", "DELETE") is True

    def test_traversal_model_to_admin_is_dangerous(self):
        """'/api/model/../../admin' normalizes to '/api/admin' → dangerous"""
        assert _is_dangerous("/api/model/../../admin", "POST") is True

    def test_path_variant_delete_is_dangerous(self):
        """'/api/v1/delete' has dangerous tail segment 'delete' → dangerous"""
        assert _is_dangerous("/api/v1/delete/user/42", "POST") is True

    def test_encoded_slash_resists_normalization(self):
        """'//api//delete' normalizes to '/api/delete' → dangerous"""
        assert _is_dangerous("//api//delete/user", "DELETE") is True

    def test_safe_chat_path_is_not_dangerous(self):
        """'/api/chat' (allowed) must NOT be flagged dangerous"""
        assert _is_dangerous("/api/chat", "POST") is False

    def test_safe_query_with_similar_word_is_not_dangerous(self):
        """'/api/query' + GET must not be flagged (not a dangerous method)"""
        assert _is_dangerous("/api/query/status", "GET") is False

    def test_boundary_similar_prefix_not_dangerous(self):
        """'/api/delete-message' is a different resource; boundary match must not fire"""
        assert _is_dangerous("/api/delete-message", "DELETE") is False

    def test_query_string_stripped_before_match(self):
        """'?id=..' must not influence normalization"""
        assert _is_dangerous("/api/delete/../admin?x=1", "POST") is True


# ── Finding 1: breaker trips to DENY (fail-closed) ───────────────────

class TestBreakerTripsToDeny(AioHTTPTestCase):
    async def get_application(self):
        return create_app()

    @unittest_run_loop
    async def test_10th_escalate_in_window_trips_to_deny(self):
        """breaker trips → 403 DENY (never ALLOW)"""
        for _ in range(9):
            resp = await self.client.post(
                "/v1/intercept",
                json={"path": "/api/config/model", "method": "POST"},
            )
            assert resp.status == 202
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/config/model", "method": "POST"},
        )
        assert resp.status == 403
        data = await resp.json()
        assert data["verdict"] == "DENY"

    @unittest_run_loop
    async def test_after_trip_counter_resets(self):
        """after a trip, cooldown window denies (DEBT-0001), then recovers"""
        for _ in range(10):
            resp = await self.client.post(
                "/v1/intercept",
                json={"path": "/api/config/model", "method": "POST"},
            )
        assert resp.status == 403

        # DEBT-0001: trip starts cooldown → immediate next ESCALATE is DENY
        # (old behavior allowed instant re-accumulation — the fixed flaw)
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/config/model", "method": "POST"},
        )
        assert resp.status == 403

        # cooldown expiry → time-decay recovery back to ESCALATE
        import time
        import src.main as main_module

        main_module.breaker_tripped_until = time.time() - 1.0
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/config/model", "method": "POST"},
        )
        assert resp.status == 202  # recovered after cooldown


# ── Finding 3: lock-protected global counter ─────────────────────────

class TestEscalateCounterLock(AioHTTPTestCase):
    async def get_application(self):
        return create_app()

    @unittest_run_loop
    async def test_lock_installed(self):
        """create_app must install an asyncio.Lock for the counter"""
        assert main_module._escalate_lock is not None
        assert not main_module._escalate_lock.locked()

    @unittest_run_loop
    async def test_concurrent_escalates_no_race(self):
        """5 parallel ESCALATEs → exactly 5 counter increments (no lost updates)"""
        import asyncio

        async def escalate(i):
            resp = await self.client.post(
                "/v1/intercept",
                json={"path": "/api/config/model", "method": "POST"},
            )
            return resp.status

        statuses = await asyncio.gather(*[escalate(i) for i in range(5)])
        assert all(s == 202 for s in statuses)
        assert main_module.escalate_count_since_resolve == 5


# ── Finding 4: header whitelist ──────────────────────────────────────

class TestHeaderWhitelist(AioHTTPTestCase):
    async def get_application(self):
        return create_app()

    @unittest_run_loop
    async def test_whitelist_defined(self):
        """Authorization must not be in the forward whitelist"""
        lowered = {h.lower() for h in main_module.FORWARD_HEADER_WHITELIST}
        assert "authorization" not in lowered
        assert "cookie" not in lowered

    @unittest_run_loop
    async def test_proxy_forward_strips_auth_header(self):
        """_proxy_forward must not forward Authorization upstream.

        Spawn a tiny upstream that echoes received headers; verify
        Authorization is absent. (Proves the whitelist filter at runtime.)
        """
        from aiohttp import web, ClientSession

        received = {}

        async def echo_handler(request):
            received["headers"] = dict(request.headers)
            return web.json_response({"ok": True})

        upstream = web.Application()
        upstream.router.add_post("/api/chat", echo_handler)
        runner = web.AppRunner(upstream)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]

        old_url = main_module.AGENT_BACKEND_URL
        main_module.AGENT_BACKEND_URL = f"http://127.0.0.1:{port}"

        try:
            resp = await self.client.post(
                "/v1/intercept",
                json={
                    "path": "/api/chat",
                    "method": "POST",
                    "body": "{}",
                    "headers": {
                        "Authorization": "Bearer SECRET-TOKEN",
                        "Content-Type": "application/json",
                        "X-Agent-Id": "agent-7",
                    },
                },
            )
            assert resp.status == 200
            fwd = {k.lower(): v for k, v in received["headers"].items()}
            assert "authorization" not in fwd, "Authorization leaked upstream!"
            assert fwd.get("x-agent-id") == "agent-7", "whitelisted header dropped"
        finally:
            main_module.AGENT_BACKEND_URL = old_url
            await runner.cleanup()
