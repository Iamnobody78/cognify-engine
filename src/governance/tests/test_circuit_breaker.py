"""Circuit breaker cooldown + distributed-trigger tests (DEBT-0001).

REWRITTEN from the old time-decay tests. The old semantics
('interval >300s does not accumulate') CONTRADICTED DEBT-0001:
an attacker could avoid the breaker by spacing ESCALATEs >300s apart.

New contract (TASK-REAL-002):
1. trip starts a cooldown window (CIRCUIT_COOLDOWN_SECONDS=30): during it,
   every ESCALATE-matching request is DENY (fail-closed), no re-accumulation.
2. cooldown expires → breaker auto-recovers (time decay): ESCALATE again.
3. distributed triggers accumulate: the counter is NOT reset by elapsed time;
   only ALLOW or a trip resets it. 9 slow ESCALATEs + 10th → trip.
4. ALLOW resets counter AND clears breaker_tripped_until.
"""

import time

from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

import src.main as main_module
from src.main import create_app


class TestCircuitBreakerCooldown(AioHTTPTestCase):
    async def get_application(self):
        return create_app()

    @unittest_run_loop
    async def test_continuous_burst_still_trips(self):
        """10 ESCALATEs in quick succession → 10th trips to DENY (fail-closed)."""
        for i in range(9):
            resp = await self.client.post(
                "/v1/intercept",
                json={"path": "/api/config/model", "method": "POST"},
            )
            assert resp.status == 202, f"iteration {i}: expected 202, got {resp.status}"

        # 10th within the window → trips to DENY
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/config/model", "method": "POST"},
        )
        assert resp.status == 403
        data = await resp.json()
        assert data["verdict"] == "DENY"

    @unittest_run_loop
    async def test_trip_starts_cooldown(self):
        """Immediately after a trip, the next ESCALATE is DENY (cooldown active).

        DEBT-0001 fix: old code reset the counter to 0 on trip and allowed
        immediate re-accumulation. Now the cooldown window denies everything.
        """
        for _ in range(10):
            resp = await self.client.post(
                "/v1/intercept",
                json={"path": "/api/config/model", "method": "POST"},
            )
        assert resp.status == 403, "10th must trip"

        # Right after trip, cooldown must still be active → DENY, not ESCALATE
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/config/model", "method": "POST"},
        )
        assert resp.status == 403, f"expected DENY during cooldown, got {resp.status}"
        data = await resp.json()
        assert data["verdict"] == "DENY"

    @unittest_run_loop
    async def test_cooldown_expires_and_recovers(self):
        """After cooldown expiry the breaker auto-recovers (time decay)."""
        # Trip the breaker
        for _ in range(10):
            await self.client.post(
                "/v1/intercept",
                json={"path": "/api/config/model", "method": "POST"},
            )

        # Simulate cooldown expiry
        main_module.breaker_tripped_until = time.time() - 1.0

        # Next ESCALATE → back to ESCALATE (not permanent stay-open)
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/config/model", "method": "POST"},
        )
        assert resp.status == 202, f"expected ESCALATE after cooldown, got {resp.status}"
        data = await resp.json()
        assert data["verdict"] == "ESCALATE"

    @unittest_run_loop
    async def test_distributed_trigger_accumulates(self):
        """9 slow ESCALATEs (400s apart) still accumulate → 10th trips.

        DEBT-0001 core: distributed slow triggers must NOT bypass the breaker.
        Counter is only reset by ALLOW or trip, NOT by elapsed time.
        """
        for _ in range(9):
            resp = await self.client.post(
                "/v1/intercept",
                json={"path": "/api/config/model", "method": "POST"},
            )
            assert resp.status == 202
            # Simulate 400s between each trigger
            main_module.last_escalate_time = time.time() - 400.0

        # 10th slow trigger — MUST trip now (old code: stayed ESCALATE)
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/config/model", "method": "POST"},
        )
        assert resp.status == 403, f"expected DENY on 10th distributed trigger, got {resp.status}"
        data = await resp.json()
        assert data["verdict"] == "DENY"

    @unittest_run_loop
    async def test_allow_resets_counter(self):
        """An ALLOW request in between resets the breaker counter."""
        for _ in range(5):
            resp = await self.client.post(
                "/v1/intercept",
                json={"path": "/api/config/model", "method": "POST"},
            )
            assert resp.status == 202

        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/chat", "method": "POST"},
        )
        assert resp.status == 200
        assert main_module.escalate_count_since_resolve == 0

        for _ in range(5):
            resp = await self.client.post(
                "/v1/intercept",
                json={"path": "/api/config/model", "method": "POST"},
            )
            assert resp.status == 202

    @unittest_run_loop
    async def test_tripped_until_reset_on_allow(self):
        """ALLOW clears breaker_tripped_until so ESCALATE recovers immediately."""
        for _ in range(10):
            await self.client.post(
                "/v1/intercept",
                json={"path": "/api/config/model", "method": "POST"},
            )

        # ALLOW should clear the cooldown
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/chat", "method": "POST"},
        )
        assert resp.status == 200
        assert main_module.breaker_tripped_until == 0.0

        # Next ESCALATE → 202 (recovered)
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/config/model", "method": "POST"},
        )
        assert resp.status == 202, f"expected ESCALATE after ALLOW reset, got {resp.status}"
