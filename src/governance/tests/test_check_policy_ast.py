"""DEBT-0006 contract tests: exact-token matching in scripts/check_policy.py.

The AST visitor must flag EXACT action keys ('allow', 'deny', 'block',
'escalate', 'rule'), never substring keys:

  1. {'allow_retry': 3, 'deny_attempt': 5, 'blocked_by': True}
     -> NO violation (substring keys are false positives under old matching)
  2. {'allow': 'x', 'deny': 'y'} -> violation (2 exact keys, len>=2 threshold)
  3. {'allow': 'x'} -> NOT a violation (1 key < 2)
  4. clean code -> no violation

Uses check_policy.scan_file(path) -> list of violations (empty == exit 0).

NOTE: no backslash-n escapes in this file on purpose - the MCP transport
(scripts/mcp_client.py line 89) converts every literal backslash-n sequence to
a real newline, so all multi-line strings here use triple-quoted literals.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT))

import check_policy  # noqa: E402


def _write_py(tmp_path, name, code):
    p = tmp_path / name
    p.write_text(code, encoding="utf-8")
    return p  # scan_file expects a Path (it calls .read_text())


class TestExactTokenMatching:
    def test_no_false_positive_on_substring_keys(self, tmp_path):
        """Substring keys ('allow_retry', 'deny_attempt', 'blocked_by') must
        NOT be flagged - this is the DEBT-0006 fix (old 'in' matching tripped
        on them)."""
        path = _write_py(tmp_path, "substring_keys.py", """\
# fixture: substring keys must NOT be treated as action keys
CONFIG = {'allow_retry': 3, 'deny_attempt': 5, 'blocked_by': True}
""")
        assert check_policy.scan_file(path) == []

    def test_detects_exact_action_keys(self, tmp_path):
        """Two EXACT action keys still produce a violation (old capability
        preserved)."""
        path = _write_py(tmp_path, "exact_keys.py", """\
ACTIONS = {'allow': 'x', 'deny': 'y'}
""")
        violations = check_policy.scan_file(path)
        assert len(violations) == 1  # one hardcoded action dict

    def test_single_exact_key_not_enough(self, tmp_path):
        """One exact key only => under the len>=2 threshold => NOT a violation."""
        path = _write_py(tmp_path, "single_key.py", """\
ACTIONS = {'allow': 'x'}
""")
        assert check_policy.scan_file(path) == []

    def test_clean_file(self, tmp_path):
        """No action dicts at all => exit 0 (no violations)."""
        path = _write_py(tmp_path, "clean.py", """\
def handler(path):
    return path.upper()
""")
        assert check_policy.scan_file(path) == []
