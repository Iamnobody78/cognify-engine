"""Real HTTP integration tests — starts the gateway, sends real requests.

These tests verify actual HTTP behavior:
- ALLOW when no policy matches
- DENY when block rule matches
- ESCALATE when escalate rule matches
- Circuit breaker kicks in after consecutive escalations
"""

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from src.main import create_app


class TestInterceptHTTP(AioHTTPTestCase):
    """Integration tests using real aiohttp test client."""

    async def get_application(self):
        return create_app()

    @unittest_run_loop
    async def test_health_endpoint_returns_ok(self):
        resp = await self.client.get("/v1/health")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.4.0"
        assert "uptime_seconds" in data

    @unittest_run_loop
    async def test_allow_when_no_policy_matches(self):
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/unknown", "method": "GET"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["verdict"] == "ALLOW"
        assert "无匹配策略" in data["reason"]

    @unittest_run_loop
    async def test_deny_when_block_rule_matches(self):
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/delete/user", "method": "POST"},
        )
        assert resp.status == 403
        data = await resp.json()
        assert data["verdict"] == "DENY"
        assert "block-delete" in data["matched_rule"]

    @unittest_run_loop
    async def test_deny_sudo_operation(self):
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/admin/sudo", "method": "POST"},
        )
        assert resp.status == 403
        data = await resp.json()
        assert data["verdict"] == "DENY"
        assert "sudo" in data["reason"].lower()

    @unittest_run_loop
    async def test_escalate_when_config_write_rule_matches(self):
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/config/model", "method": "POST"},
        )
        assert resp.status == 202
        data = await resp.json()
        assert data["verdict"] == "ESCALATE"
        assert "escalate-config-write" in data["matched_rule"]

    @unittest_run_loop
    async def test_allow_explicitly_allowed_endpoint(self):
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/chat", "method": "POST"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["verdict"] == "ALLOW"
        assert "allow-chat" in data["matched_rule"]

    @unittest_run_loop
    async def test_decision_is_persisted_and_retrievable(self):
        # make a request
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/chat", "method": "POST", "agent_id": "test-agent-1"},
        )
        assert resp.status == 200
        data = await resp.json()
        decision_id = data["decision_id"]

        # retrieve decisions
        resp2 = await self.client.get("/v1/decisions?limit=5")
        assert resp2.status == 200
        decisions_data = await resp2.json()
        assert decisions_data["total"] >= 1
        # our decision should be in the list
        ids = [d["id"] for d in decisions_data["decisions"]]
        assert decision_id in ids

    @unittest_run_loop
    async def test_circuit_breaker_after_consecutive_escalations(self):
        """After 10 consecutive ESCALATE verdicts, the circuit breaker
        trips to DENY (fail-closed) — AUDIT-0005: never ALLOW on breaker trip."""
        for i in range(9):
            resp = await self.client.post(
                "/v1/intercept",
                json={"path": "/api/config/model", "method": "POST"},
            )
            assert resp.status == 202  # still escalating
            data = await resp.json()
            assert data["verdict"] == "ESCALATE"

        # 10th request → circuit breaker trips → DENY
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/config/model", "method": "POST"},
        )
        assert resp.status == 403  # fail-closed
        data = await resp.json()
        assert data["verdict"] == "DENY"
        assert "熔断" in data["reason"] or "circuit" in data["reason"].lower()

    @unittest_run_loop
    async def test_invalid_json_returns_400(self):
        resp = await self.client.post(
            "/v1/intercept",
            data="not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400

    @unittest_run_loop
    async def test_missing_required_fields_returns_422(self):
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/foo"},  # missing "method"
        )
        assert resp.status == 422
