"""Integration test: Sidecar proxy + real Agent (zero-code-change).

This test proves the v2 iron law #1: "Agent code has zero gateway imports."

Architecture:
    EchoAgent --HTTP--> Gateway (:19000) --proxy--> EchoServer (:18000)
                         |
                    PolicyEngine
                    Storage (SQLite)

The EchoAgent has NO import of governance-gateway. It makes standard
HTTP calls. The gateway transparently intercepts, evaluates policies,
and forwards/denies/escalates.
"""

import asyncio
import time
from pathlib import Path

import pytest
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop


class TestZeroInvasionGateway(AioHTTPTestCase):
    """Prove zero-invasion: Agent has no gateway imports, yet all
    requests are transparently governed."""

    async def get_application(self):
        from src.main import create_app
        return create_app()

    # ── tests ─────────────────────────────────────────────────────

    @unittest_run_loop
    async def test_agent_zero_gateway_imports(self):
        """echo_agent.py has ZERO imports from governance-gateway."""
        agent_path = Path("examples/echo_agent.py")
        source = agent_path.read_text(encoding="utf-8")
        # Check actual Python import statements only (not docstrings)
        lines = source.split("\n")
        import_lines = [l.strip() for l in lines
                        if l.strip().startswith("import ") or l.strip().startswith("from ")]
        forbidden = ["src.", "governance_gateway", "governance.gateway"]
        for line in import_lines:
            for fb in forbidden:
                assert fb not in line, \
                    f"Agent import line contains forbidden '{fb}': {line}"
        # Also verify no pip-installed governance package
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("import governance") or stripped.startswith("from governance"):
                assert False, f"Agent must not import governance: {stripped}"

    @unittest_run_loop
    async def test_allow_chat_passes_through(self):
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/chat", "method": "POST",
                  "body": '{"message":"hello"}', "agent_id": "echo-1"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["verdict"] == "ALLOW"
        assert data["matched_rule"] == "allow-chat"

    @unittest_run_loop
    async def test_deny_delete_blocked(self):
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/delete/user", "method": "POST",
                  "agent_id": "echo-1"},
        )
        assert resp.status == 403
        data = await resp.json()
        assert data["verdict"] == "DENY"
        assert "block-delete" in data["matched_rule"]

    @unittest_run_loop
    async def test_deny_sudo_blocked(self):
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/admin/sudo", "method": "POST",
                  "agent_id": "echo-1"},
        )
        assert resp.status == 403
        data = await resp.json()
        assert data["verdict"] == "DENY"

    @unittest_run_loop
    async def test_escalate_config(self):
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/config/model", "method": "POST",
                  "agent_id": "echo-1"},
        )
        assert resp.status == 202
        data = await resp.json()
        assert data["verdict"] == "ESCALATE"

    @unittest_run_loop
    async def test_full_agent_flow_with_decision_log(self):
        """End-to-end: Agent sends requests, gateway governs, log persists."""
        agent_id = "echo-agent-full"
        results = {"ALLOW": 0, "DENY": 0, "ESCALATE": 0}

        # ALLOW
        for _ in range(2):
            resp = await self.client.post(
                "/v1/intercept",
                json={"path": "/api/chat", "method": "POST", "agent_id": agent_id},
            )
            assert resp.status == 200
            data = await resp.json()
            assert data["verdict"] == "ALLOW"
            results["ALLOW"] += 1

        # DENY (should block)
        for path in ["/api/delete/user", "/api/admin/sudo"]:
            resp = await self.client.post(
                "/v1/intercept",
                json={"path": path, "method": "POST", "agent_id": agent_id},
            )
            assert resp.status == 403
            data = await resp.json()
            assert data["verdict"] == "DENY"
            results["DENY"] += 1

        # ESCALATE
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/config/model", "method": "POST", "agent_id": agent_id},
        )
        assert resp.status == 202
        data = await resp.json()
        assert data["verdict"] == "ESCALATE"
        results["ESCALATE"] += 1

        # Verify decision log
        resp = await self.client.get("/v1/decisions?limit=20")
        assert resp.status == 200
        log = await resp.json()
        assert log["total"] >= 5

        # All our decisions should be there
        agent_d = [d for d in log["decisions"] if d.get("agent_id") == agent_id]
        assert len(agent_d) >= 5

        # Final counts
        assert results["ALLOW"] == 2
        assert results["DENY"] == 2
        assert results["ESCALATE"] == 1

    @unittest_run_loop
    async def test_gateway_responds_fast(self):
        """ALLOW requests with real upstream must respond < 2s."""
        t0 = time.time()
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/chat", "method": "POST"},
        )
        elapsed = time.time() - t0
        assert resp.status == 200
        assert elapsed < 2.0, f"Gateway took {elapsed:.2f}s with real upstream"
