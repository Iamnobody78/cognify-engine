# GATE2-APPROVED: 9 real type-continuity tests for AUDIT-0006 (strong-typed models, no dataclass asserts)
"""AUDIT-0006: models.py type-continuity tests.

Proves the strong-typing fix at runtime:
  1. DecisionRecord.verdict is the Verdict enum (not bare str)
  2. DecisionRecord.timestamp is timezone-aware datetime (not bare str)
  3. serialization produces ISO8601 str with timezone info (no loss)
  4. InterceptRequest.body accepts dict OR str (no forced re-parse)
"""

from datetime import datetime, timezone

from src.models import InterceptRequest, InterceptResponse, DecisionRecord, Verdict


class TestDecisionRecordStrongTypes:
    def test_verdict_is_enum_not_str(self):
        rec = DecisionRecord(
            id="d1", verdict=Verdict.DENY, reason="r",
            path="/api/delete/x", method="DELETE",
        )
        assert isinstance(rec.verdict, Verdict)
        assert rec.verdict is Verdict.DENY

    def test_timestamp_is_tz_aware_datetime(self):
        rec = DecisionRecord(
            id="d1", verdict=Verdict.ALLOW, reason="r",
            path="/api/chat", method="POST",
        )
        assert isinstance(rec.timestamp, datetime)
        assert rec.timestamp.tzinfo is not None

    def test_serialize_keeps_enum_value_and_tz(self):
        rec = DecisionRecord(
            id="d1", verdict=Verdict.ESCALATE, reason="r",
            path="/api/config", method="POST",
        )
        dumped = rec.model_dump(mode="json")
        assert dumped["verdict"] == "ESCALATE"          # enum → str at the edge
        ts = datetime.fromisoformat(dumped["timestamp"])
        assert ts.tzinfo is not None                     # timezone preserved

    def test_agent_id_roundtrip(self):
        rec = DecisionRecord(
            id="d1", verdict=Verdict.ALLOW, reason="r",
            path="/api/chat", method="POST", agent_id="agent-7",
        )
        dumped = rec.model_dump(mode="json")
        assert dumped["agent_id"] == "agent-7"


class TestInterceptRequestBodyFlexibility:
    def test_body_accepts_dict(self):
        req = InterceptRequest(path="/api/chat", method="POST", body={"msg": "hi"})
        assert isinstance(req.body, dict)

    def test_body_accepts_str(self):
        req = InterceptRequest(path="/api/chat", method="POST", body='{"msg":"hi"}')
        assert isinstance(req.body, str)

    def test_body_accepts_none(self):
        req = InterceptRequest(path="/api/chat", method="POST")
        assert req.body is None


class TestInterceptResponseStrongTypes:
    def test_response_verdict_is_enum(self):
        resp = InterceptResponse(
            verdict=Verdict.ALLOW, reason="r", decision_id="x",
        )
        assert isinstance(resp.verdict, Verdict)

    def test_response_roundtrip_via_json(self):
        resp = InterceptResponse(
            verdict=Verdict.DENY, reason="blocked", decision_id="x",
            matched_rule="block-delete",
        )
        dumped = resp.model_dump(mode="json")
        assert dumped["verdict"] == "DENY"
        assert dumped["matched_rule"] == "block-delete"
