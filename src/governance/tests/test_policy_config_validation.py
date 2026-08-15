"""P3 exception-path tests (external critique #2.1 / #3.1 / #5.3).

Covered:
  - invalid action values (typo / empty) must FAIL CLOSED at load time,
    not silently fall through the gateway's else->ALLOW branch
  - lowercase YAML actions must normalize to ALLOW/DENY/ESCALATE
    (previously "deny" would never match `if rule.action == "DENY"`)
  - Storage.save is now called via asyncio.to_thread on the event loop →
    cross-thread access to the shared sqlite3 connection must be
    serialized by the internal threading.Lock (no lost/partial writes)
"""

import threading

import pytest
import yaml

from src.policy import PolicyEngine, Rule


def _write_yaml(tmp_path, data: dict) -> str:
    p = tmp_path / "policies.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    return str(p)


class TestInvalidActionFailsClosed:
    def test_typo_action_raises_value_error(self, tmp_path):
        """'ALLOWWW' would previously load silently and act as ALLOW (the
        gateway else-branch). Now it must refuse to start."""
        p = _write_yaml(tmp_path, {"rules": [
            {"name": "r1", "path_pattern": "/x", "action": "ALLOWWW"},
        ]})
        with pytest.raises(ValueError, match="invalid action"):
            PolicyEngine(config_path=p)

    def test_empty_action_raises(self, tmp_path):
        p = _write_yaml(tmp_path, {"rules": [
            {"name": "r1", "path_pattern": "/x", "action": ""},
        ]})
        with pytest.raises(ValueError, match="invalid action"):
            PolicyEngine(config_path=p)

    def test_lowercase_action_normalized_to_deny(self, tmp_path):
        """A DENY rule written as 'deny' must still DENY (previously the
        strict == comparison silently turned it into ALLOW)."""
        p = _write_yaml(tmp_path, {"rules": [
            {"name": "r1", "path_pattern": "/api/admin/*", "action": "deny"},
        ]})
        engine = PolicyEngine(config_path=p)
        rule = engine.evaluate("/api/admin/users", "GET")
        assert rule is not None and rule.action == "DENY"

    def test_valid_actions_still_load(self, tmp_path):
        p = _write_yaml(tmp_path, {"rules": [
            {"name": "deny-admin", "path_pattern": "/api/admin/*", "action": "DENY"},
            {"name": "allow-health", "path_pattern": "/api/health", "action": "ALLOW"},
        ]})
        engine = PolicyEngine(config_path=p)
        assert len(engine.rules) == 2
        assert engine.evaluate("/api/admin/x", "GET").action == "DENY"
        assert engine.evaluate("/api/health", "GET").action == "ALLOW"

    def test_rule_direct_construction_validation(self):
        with pytest.raises(ValueError, match="invalid action"):
            Rule(name="x", path_pattern="/y", action="DENYy")


class TestStorageThreadSafety:
    """Storage.save runs via asyncio.to_thread now — 32 threads hammering the
    shared connection must all persist under the internal lock."""

    def test_concurrent_saves_all_persisted(self):
        from src.storage import Storage

        storage = Storage(db_path=":memory:")
        errors = []

        def _save(i):
            try:
                storage.save({
                    "id": f"id-{i}", "verdict": "ALLOW", "reason": "t",
                    "matched_rule": None,
                    "timestamp": f"2026-08-03T00:00:{i:02d}",
                    "path": f"/p/{i}", "method": "GET", "agent_id": None,
                })
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=_save, args=(i,)) for i in range(32)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors, f"saves failed: {errors}"
        assert storage.count() == 32

    def test_get_by_id_roundtrip_after_threaded_save(self):
        from src.storage import Storage

        storage = Storage(db_path=":memory:")
        storage.save({
            "id": "abc", "verdict": "DENY", "reason": "dangerous",
            "matched_rule": "deny-del", "timestamp": "2026-08-03T12:00:00",
            "path": "/api/delete/x", "method": "DELETE", "agent_id": None,
        })
        row = storage.get_by_id("abc")
        assert row is not None and row["verdict"] == "DENY"
