#!/usr/bin/env python3
"""Daily health score for the governance gateway (audit closed loop).

Computes a 0-100 score from four real signals:
  G1  test suite            : pass ratio from pytest (real runtime result)
  G2  test quality (GATE 1) : dataclass-assert scan (no fake tests)
  G3  policy consistency    : policy_probe + policy_sync drift check
  G4  security scan (GATE6) : anti-pattern findings in src/

Each gate is executed for real (subprocess) — no canned numbers.
Score = 25 * G1 + 25 * G2 + 25 * G3 + 25 * G4, each gate ∈ [0,1].

Usage:
  python scripts/health_score.py            # run all gates, print score
  python scripts/health_score.py --json     # JSON output (for CI artifact)
"""

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def run(cmd: list, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=REPO, capture_output=True, text=True, timeout=timeout,
    )


def gate_tests() -> float:
    """G1: pytest pass ratio (0.0 if any collection error)."""
    r = run([sys.executable, "-m", "pytest", "tests/", "-q", "--no-header"])
    if r.returncode not in (0, 1):
        return 0.0
    # parse "53 passed" / "2 failed" from the summary tail (regex, robust
    # to separator lines and color codes)
    m = re.search(r"(\d+)\s+passed", r.stdout + r.stderr)
    n_pass = int(m.group(1)) if m else 0
    m = re.search(r"(\d+)\s+failed", r.stdout + r.stderr)
    n_fail = int(m.group(1)) if m else 0
    total = n_pass + n_fail
    return n_pass / total if total else 0.0


def gate_quality() -> float:
    """G2: GATE 1 scanner — 1.0 if no dataclass asserts found."""
    r = run([sys.executable, "scripts/check_test_quality.py"])
    return 1.0 if r.returncode == 0 else 0.0


def gate_policy() -> float:
    """G3: policy consistency — both policy_probe and policy_sync must pass."""
    r1 = run([sys.executable, "examples/policy_probe.py"])
    r2 = run([sys.executable, "scripts/policy_sync.py"])
    return 1.0 if (r1.returncode == 0 and r2.returncode == 0) else 0.0


def gate_security() -> float:
    """G4: GATE 6 anti-pattern scan — 1.0 if clean, scaled by severity."""
    r = run([sys.executable, "scripts/meta_security_scanner.py", "src"])
    if r.returncode == 0:
        return 1.0
    findings = r.stdout.count("[HIGH]") + r.stdout.count("[MEDIUM]")
    return max(0.0, 1.0 - 0.2 * findings)


def main() -> int:
    results = {
        "tests": gate_tests(),
        "quality": gate_quality(),
        "policy": gate_policy(),
        "security": gate_security(),
    }
    score = 25 * (results["tests"] + results["quality"]
                  + results["policy"] + results["security"])
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "score": round(score, 1),
        "gates": {k: round(v, 3) for k, v in results.items()},
    }

    if "--json" in sys.argv:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Health score: {payload['score']}/100")
        for k, v in payload["gates"].items():
            status = "PASS" if v >= 1.0 else ("WARN" if v >= 0.5 else "FAIL")
            print(f"  [{status}] {k}: {v:.3f}")

    # write daily report for the audit closed loop
    out = Path(REPO) / ".aionui" / "audit"
    out.mkdir(parents=True, exist_ok=True)
    (out / "health_score.md").write_text(
        f"# Health Score — {payload['timestamp']}\n\n"
        f"**Score: {payload['score']}/100**\n\n"
        + "\n".join(f"- {k}: {v:.3f}" for k, v in payload["gates"].items())
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
