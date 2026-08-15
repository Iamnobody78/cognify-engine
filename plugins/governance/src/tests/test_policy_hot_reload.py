"""DEBT-0005 contract tests: PolicyEngine hot-reload.

These tests pin the CONTRACT the Builder must implement (Coordinator rules in
favor of the tests if implementation contradicts them):

  * PolicyEngine(path_or_none):
      - given a path -> loads that file, records self._config_path
      - None/omitted -> keeps existing default behavior (config/policies.yaml)
  * reload() -> bool:
      - True on successful re-read
      - False on missing file or parse error, AND OLD RULES ARE KEPT
  * maybe_reload() -> bool:
      - False when file mtime unchanged
      - True when mtime changed AND reload succeeded

Imported as `from src.policy import PolicyEngine` - the established pattern in
this repo (editable-install src package; tests/test_policy_config_validation.py).

NOTE: no backslash-n escapes in this file on purpose - the MCP transport
(scripts/mcp_client.py line 89) converts every literal backslash-n sequence to
a real newline, so all multi-line strings here use triple-quoted literals.
"""

import os
import time
from pathlib import Path

from src.policy import PolicyEngine

# Minimal valid governance policy per contract.
MINIMAL_YAML = """name: x
version: '1'
rules: []
"""


def _write(path, content):
    path.write_text(content, encoding="utf-8")


def _bump_mtime(path, seconds=5.0):
    """Force a distinct future mtime - no sleeps (tests must stay fast)."""
    t = time.time() + seconds
    os.utime(path, (t, t))


class TestHotReloadContract:
    def test_initial_load(self, tmp_path):
        """Engine constructed from a file loads its rules; evaluate works."""
        p = tmp_path / "policies.yaml"
        _write(p, MINIMAL_YAML)
        engine = PolicyEngine(p)
        assert engine._config_path == str(p)
        assert engine.config.version == "1"
        # no rules => nothing matches => ALLOW (evaluate returns None)
        assert engine.evaluate("/anything", "GET") is None

    def test_none_or_omitted_path_keeps_default(self):
        """PolicyEngine() / PolicyEngine(None) must keep the default behavior
        (load config/policies.yaml), not crash, and record a path."""
        for engine in (PolicyEngine(), PolicyEngine(None)):
            assert isinstance(engine._config_path, str)
            assert engine.config is not None
            assert isinstance(engine.rules, list)
            # evaluate must work without raising
            engine.evaluate("/", "GET")

    def test_mtime_unchanged_no_reload(self, tmp_path):
        """maybe_reload() right after init: mtime unchanged => False."""
        p = tmp_path / "policies.yaml"
        _write(p, MINIMAL_YAML)
        engine = PolicyEngine(p)
        assert engine.maybe_reload() is False

    def test_reload_picks_up_changes(self, tmp_path):
        """File edited (version 2 + DENY rule) + mtime bumped => maybe_reload()
        True and the NEW rule is active WITHOUT restart (the DEBT-0005 fix)."""
        p = tmp_path / "policies.yaml"
        _write(p, MINIMAL_YAML)
        engine = PolicyEngine(p)
        assert engine.evaluate("/api/admin/x", "GET") is None

        _write(p, """name: x
version: '2'
rules:
  - name: deny-admin
    path_pattern: /api/admin/*
    action: DENY
""")
        _bump_mtime(p)

        assert engine.maybe_reload() is True
        assert engine.config.version == "2"
        rule = engine.evaluate("/api/admin/x", "GET")
        assert rule is not None and rule.action == "DENY"

    def test_reload_missing_file_keeps_old(self, tmp_path):
        """File deleted => reload() False, OLD rules still in effect."""
        p = tmp_path / "policies.yaml"
        _write(p, MINIMAL_YAML)
        engine = PolicyEngine(p)
        p.unlink()

        assert engine.reload() is False
        assert engine.config.version == "1"
        assert engine.evaluate("/anything", "GET") is None  # old behavior

    def test_reload_invalid_yaml_keeps_old(self, tmp_path):
        """Garbage YAML + mtime bump => reload() False, OLD rules kept.
        (maybe_reload is True only when mtime changed AND reload succeeded,
        so a failed reload must not surface new state either.)"""
        p = tmp_path / "policies.yaml"
        _write(p, MINIMAL_YAML)
        engine = PolicyEngine(p)

        _write(p, "not: [valid")
        _bump_mtime(p)

        assert engine.reload() is False
        assert engine.config.version == "1"
        assert engine.evaluate("/anything", "GET") is None
