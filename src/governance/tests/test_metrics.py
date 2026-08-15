"""Test the /metrics Prometheus endpoint (Stage C1 prerequisite)."""

import re

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from src.main import create_app


class MetricsEndpointTest(AioHTTPTestCase):
    async def get_application(self) -> web.Application:
        return create_app()

    @unittest_run_loop
    async def test_metrics_exposes_all_gauges(self):
        resp = await self.client.get("/metrics")
        assert resp.status == 200
        assert "text/plain" in resp.headers.get("Content-Type", "")
        body = await resp.text()

        required = [
            "governance_uptime_seconds",
            "governance_decisions_total",
            "governance_escalations_since_resolve",
            "governance_breaker_tripped",
            "governance_breaker_remaining_seconds",
            "governance_ast_languages",
            "governance_pending_flush",
        ]
        for name in required:
            assert name in body, f"metric {name} missing"

        # every metric line must carry a numeric value
        for line in body.splitlines():
            if line.startswith("governance_"):
                assert re.match(r"^governance_\w+ [-0-9.]+$", line), \
                    f"non-numeric value: {line}"

    @unittest_run_loop
    async def test_metrics_has_help_and_type_lines(self):
        resp = await self.client.get("/metrics")
        body = await resp.text()
        assert "# HELP governance_uptime_seconds" in body
        assert "# TYPE governance_breaker_tripped gauge" in body

    @unittest_run_loop
    async def test_breaker_metric_tracks_state(self):
        # escalate via /v1/intercept (same trigger as test_intercept.py) ->
        # breaker trips after 10 -> metric must report 1
        for i in range(10):
            await self.client.post("/v1/intercept",
                                   json={"path": "/api/config/model", "method": "POST"})
        resp = await self.client.get("/metrics")
        body = await resp.text()

        m = re.search(r"^governance_breaker_tripped (\d)", body, re.M)
        assert m is not None, "breaker metric missing"
        assert m.group(1) == "1", "breaker should be tripped after escalations"
