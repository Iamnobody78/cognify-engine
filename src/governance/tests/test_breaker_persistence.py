"""DEBT-0011 + DEBT-0012 regression tests.

- breaker state survives a gateway restart (persisted via SQLite, restored at
  create_app startup) — an attacker cannot reboot to bypass the cooldown.
- empty policies.yaml refuses to load (fail-closed), both direct and via
  PolicyEngine() construction with an empty config.
"""

import json
import os
import tempfile

import pytest

from src.policy import PolicyEngine
from src.storage import Storage


class TestBreakerPersistence:
    def test_save_then_load_roundtrip(self):
        s = Storage()
        s.save_breaker_state(7, 12.5, 99.0)
        assert s.load_breaker_state() == {"count": 7, "last_escalate": 12.5, "tripped_until": 99.0}
        s.close()

    def test_load_default_when_absent(self):
        s = Storage()
        assert s.load_breaker_state() == {"count": 0, "last_escalate": 0.0, "tripped_until": 0.0}
        s.close()

    def test_persisted_across_restart_file_db(self):
        # real file DB: state must survive a NEW Storage instance (restart)
        tmp = tempfile.mktemp(suffix=".db")
        try:
            s1 = Storage(db_path=tmp)
            s1.save_breaker_state(3, 4.0, 5.0)
            s1.close()
            s2 = Storage(db_path=tmp)
            assert s2.load_breaker_state() == {"count": 3, "last_escalate": 4.0, "tripped_until": 5.0}
            s2.close()
        finally:
            for suffix in ("", "-wal", "-shm"):
                try:
                    os.remove(tmp + suffix)
                except OSError:
                    pass

    def test_bad_state_returns_default(self):
        s = Storage()
        s.conn.execute("INSERT OR REPLACE INTO breaker_state (key, value) VALUES (?, ?)", ("breaker", "not-json"))
        s.conn.commit()
        assert s.load_breaker_state() == {"count": 0, "last_escalate": 0.0, "tripped_until": 0.0}
        s.close()


class TestEmptyPolicyFailClosed:
    def test_empty_yaml_raises(self):
        tmp = tempfile.mktemp(suffix=".yaml")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("")
        try:
            with pytest.raises(ValueError, match="empty"):
                PolicyEngine(config_path=tmp)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass

    def test_comment_only_yaml_raises(self):
        # YAML with only comments parses to None → must also fail-closed
        tmp = tempfile.mktemp(suffix=".yaml")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("# nothing here\n")
        try:
            with pytest.raises(ValueError, match="empty"):
                PolicyEngine(config_path=tmp)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass

    def test_valid_yaml_still_loads(self):
        tmp = tempfile.mktemp(suffix=".yaml")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("name: test\nversion: 0.1.0\nrules:\n  - name: r1\n    path_pattern: /api/delete\n    method: DELETE\n    action: DENY\n")
        try:
            eng = PolicyEngine(config_path=tmp)
            assert len(eng.rules) == 1
            assert eng.rules[0].action == "DENY"
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass


if __name__ == "__main__":
    import unittest

    unittest.main()
