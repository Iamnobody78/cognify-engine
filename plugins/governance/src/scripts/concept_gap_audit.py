#!/usr/bin/env python3
"""Concept gap audit — answers the meta-critique question:
"Which claimed capabilities actually have code evidence?"

For each capability claimed in README/ARCHITECTURE/docs, check whether a
real implementation file exists and whether that file is referenced by a
test. Output: a gap report listing claimed-without-evidence items.

This is an AUDIT TOOL, not a gate. It exists to make the "declared vs
implemented" gap measurable, per the meta-critique: "它在哪个文件里？
跑了哪些测试？谁调用了它？"

Usage:
  python scripts/concept_gap_audit.py            # human report
  python scripts/concept_gap_audit.py --json     # machine-readable
Exit code: 0 (report only; never blocks CI)
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple

REPO = Path(__file__).resolve().parent.parent
CLAIM_SOURCES = ["README.md", "ARCHITECTURE.md", "CRITIQUE_V2.md"]


class Gap(NamedTuple):
    concept: str
    claimed_in: str
    evidence_file: str
    has_tests: bool
    status: str   # LANDED | PARTIAL | CLAIM_ONLY


def collect_claimed_concepts() -> List[str]:
    """Extract backtick-paths + capability keywords from doc claims."""
    concepts: Dict[str, str] = {}
    for doc in CLAIM_SOURCES:
        p = REPO / doc
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        # find file paths like src/x.py, scripts/y.py, examples/z.py
        for m in re.finditer(r"`?([\w./-]+\.py)`?", text):
            path = m.group(1)
            if path.startswith(("src/", "scripts/", "examples/", "tests/")):
                concepts.setdefault(path, doc)
    return [(k, v) for k, v in concepts.items()]


def has_test_reference(impl: Path) -> bool:
    """Does any test file import or mention the implementation module?"""
    impl_stem = impl.stem  # e.g. 'policy'
    tests_dir = REPO / "tests"
    if not tests_dir.exists():
        return False
    for t in tests_dir.rglob("test_*.py"):
        text = t.read_text(encoding="utf-8", errors="replace")
        if impl_stem in text or str(impl.relative_to(REPO)) in text:
            return True
    return False


def audit() -> List[Gap]:
    gaps: List[Gap] = []
    for claimed, doc in collect_claimed_concepts():
        impl = REPO / claimed
        exists = impl.exists()
        tested = has_test_reference(impl) if exists else False
        if exists and tested:
            status = "LANDED"
        elif exists:
            status = "PARTIAL"
        else:
            status = "CLAIM_ONLY"
        gaps.append(Gap(claimed, doc, claimed, tested, status))
    return gaps


def main() -> int:
    gaps = audit()
    landed = [g for g in gaps if g.status == "LANDED"]
    partial = [g for g in gaps if g.status == "PARTIAL"]
    claim_only = [g for g in gaps if g.status == "CLAIM_ONLY"]

    report = {
        "total": len(gaps),
        "landed": len(landed),
        "partial": len(partial),
        "claim_only": len(claim_only),
        "claim_only_items": [g.concept for g in claim_only],
        "items": [g._asdict() for g in gaps],
    }

    if "--json" in sys.argv:
        print(json.dumps(report, indent=2))
    else:
        print(f"Concept gap audit: {len(landed)} landed, "
              f"{len(partial)} partial, {len(claim_only)} claim-only "
              f"(of {len(gaps)} claimed files)")
        for g in gaps:
            print(f"  [{g.status:<10}] {g.concept}  "
                  f"(claimed in {g.claimed_in}, tests: {g.has_tests})")
        if claim_only:
            print("\nCLAIM-ONLY (declared but no file):")
            for g in claim_only:
                print(f"  - {g.concept}")

    # write report for audit closed loop
    out = REPO / ".aionui" / "audit"
    out.mkdir(parents=True, exist_ok=True)
    (out / "concept_gap_report.md").write_text(
        "# Concept Gap Report\n\n"
        f"- Total claimed: {len(gaps)}\n"
        f"- Landed: {len(landed)}\n"
        f"- Partial: {len(partial)}\n"
        f"- Claim-only: {len(claim_only)}\n\n"
        + "\n".join(f"- [{g.status}] {g.concept}" for g in gaps)
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
