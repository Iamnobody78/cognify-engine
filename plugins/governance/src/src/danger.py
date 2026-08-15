"""Danger heuristics — path/method risk classification (DEBT-0002).

Single source of truth for the dangerous-path heuristic, decoupled from
src/main.py so public consumers (examples/policy_probe.py) no longer
reach into gateway private symbols.

Defense layers (v0.2.0 security hardening, AUDIT-0005):
  1. normpath normalizes '/api/delete/../admin/exec' → '/api/admin/exec',
     killing path-traversal bypasses.
  2. Boundary matching: '/api/delete-evil' does NOT match prefix '/api/delete'.
  3. Segment-level fallback: '/api/v1/delete' (path variant) hits the
     dangerous tail segment 'delete' even without an exact prefix match.
"""

import posixpath

# Shared heuristic constants — exported for policy_probe.py (single source of truth)
DANGEROUS_PREFIXES = ("/api/delete", "/api/admin", "/api/config", "/api/model")
DANGEROUS_METHODS = ("DELETE", "POST", "PUT", "PATCH")


def is_dangerous(path: str, method: str) -> bool:
    """Heuristic: operations that modify state are dangerous when uncertain.

    Behavior is identical to the former src.main._is_dangerous (DEBT-0002);
    the private name remains aliased in src.main for backward-compatible
    test imports (tests/test_security_hardening.py).
    """
    if method.upper() not in DANGEROUS_METHODS:
        return False
    normalized = posixpath.normpath(path.split("?", 1)[0])
    # 1) exact/prefix match with boundary
    for prefix in DANGEROUS_PREFIXES:
        if normalized == prefix or normalized.startswith(prefix + "/"):
            return True
    # 2) segment-level fallback: any dangerous tail segment anywhere in path
    dangerous_tails = {p.rsplit("/", 1)[-1] for p in DANGEROUS_PREFIXES}
    segments = normalized.split("/")
    if any(seg in dangerous_tails for seg in segments):
        return True
    return False


__all__ = ["DANGEROUS_PREFIXES", "DANGEROUS_METHODS", "is_dangerous"]
