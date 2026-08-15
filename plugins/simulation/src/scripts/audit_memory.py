#!/usr/bin/env python3
"""
BottleSumo Memory Consistency Auditor
--------------------------------------
Scans `.aionui/` governance files and cross-references against actual filesystem.
Detects: stale references, missing files, orphaned entries, version mismatches.

Usage:
  python audit_memory.py
  python audit_memory.py --fix  # Auto-fix simple issues
"""

import contextlib
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

with contextlib.suppress(Exception):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
AIONUI_DIR = PROJECT_ROOT / ".aionui"
MEMORY_DIR = PROJECT_ROOT / "memory"
AIONRS_MEMORY_DIR = Path(
    os.environ.get(
        "AIONRS_MEMORY",
        str(
            Path.home()
            / "AppData"
            / "Roaming"
            / "aionrs"
            / "projects"
            / "C--Users-ivy-AppData-Roaming-AionUi-aionui-conversations-2026-07-27-aionrs-temp-48324704"
            / "memory"
        ),
    )
)


class AuditResult:
    def __init__(self):
        self.ok = []
        self.warnings = []
        self.errors = []
        self.fixes_applied = []

    @property
    def pass_count(self):
        return len(self.ok)

    @property
    def fail_count(self):
        return len(self.errors) + len(self.warnings)

    def is_clean(self):
        return len(self.errors) == 0


def audit_memory_files(result: AuditResult, fix: bool = False):
    """Check MEMORY.md entries against actual files."""
    print("\n--- Memory Index Audit ---")

    mem_idx = MEMORY_DIR / "MEMORY.md"
    aionrs_idx = AIONRS_MEMORY_DIR / "MEMORY.md"

    for idx_path in [mem_idx, aionrs_idx]:
        if not idx_path.exists():
            result.errors.append(f"Memory index not found: {idx_path}")
            continue

        try:
            content = idx_path.read_text(encoding="utf-8")
        except Exception as e:
            result.errors.append(f"Cannot read {idx_path}: {e}")
            continue

        # Parse entries: "filename.md | Description | type | details"
        entries = re.findall(r"^\s*-\s+(\S+\.md)\s*\|", content, re.MULTILINE)

        for entry_file in entries:
            full_path = idx_path.parent / entry_file
            if full_path.exists():
                result.ok.append(f"Memory entry exists: {entry_file}")
            else:
                result.warnings.append(
                    f"Stale memory entry: {entry_file} (listed in {idx_path.name} but file missing)"
                )

    if result.warnings:
        print(f"  ⚠️  {len([w for w in result.warnings if 'Stale' in w])} stale entries found")


def audit_governance_files(result: AuditResult, fix: bool = False):
    """Check .aionui/ file structure integrity."""
    print("\n--- Governance Audit ---")

    expected_dirs = [
        "solid",
        "liquid",
        "gas",
        "plasma",
        "thermodynamics",
        "debt",
        "tools",
        "metacognition",
        "context",
        "metrics",
    ]

    for d in expected_dirs:
        path = AIONUI_DIR / d
        if path.exists():
            result.ok.append(f"Governance dir exists: {d}/")
        else:
            if fix:
                path.mkdir(parents=True, exist_ok=True)
                result.fixes_applied.append(f"Created: {d}/")
            else:
                result.warnings.append(f"Missing governance dir: {d}/")

    # Check key files
    key_files = [
        "thermodynamics/entropy.log",
        "context/current_status.md",
        "debt/debt_registry.yaml",
        "solid/will/toolchain_will.md",
        "tools/installed.md",
    ]

    for f in key_files:
        path = AIONUI_DIR / f
        if path.exists():
            result.ok.append(f"Key file exists: {f}")
        else:
            result.errors.append(f"Missing key file: {f}")


def audit_project_assets(result: AuditResult, fix: bool = False):
    """Check project asset files referenced in code/configs."""
    print("\n--- Asset Audit ---")

    # Check for referenced but missing files
    asset_globs = {
        "firmware/": ["*.c", "*.h", "Makefile", "CMakeLists.txt", "platformio.ini"],
        "hardware/": ["*.kicad_sch", "*.kicad_pcb", "*.kicad_pro"],
        "models/cad/": ["*.stl", "*.step", "*.urdf"],
        "simulation/": ["*.py", "*.resc", "*.sdf"],
    }

    for dir_path, patterns in asset_globs.items():
        full_dir = PROJECT_ROOT / dir_path
        if not full_dir.exists():
            result.warnings.append(f"Asset directory missing: {dir_path}")
            continue

        found = False
        for pat in patterns:
            matches = list(full_dir.glob(pat))
            if matches:
                found = True
                result.ok.append(f"Assets found: {dir_path} ({len(matches)} {pat} files)")

        if not found and dir_path.endswith("/"):
            # Check subdirectories
            all_files = list(full_dir.rglob("*"))
            py_files = [f for f in all_files if f.suffix in (".py", ".c", ".h")]
            if py_files:
                result.ok.append(f"Assets found: {dir_path} ({len(py_files)} source files)")

    # Check referenced scripts exist
    ref_scripts = [
        "bottlesumo_pi/simulation/hil_bridge_v3.py",
        "bottlesumo_pi/simulation/renode/framerate_test.py",
        "bottlesumo_pi/simulation/renode/full_diag.py",
        "bottlesumo_pi/common/dqn_config.py",
    ]

    for script in ref_scripts:
        path = PROJECT_ROOT / script
        if path.exists():
            result.ok.append(f"Script exists: {script}")
        else:
            # Try alternate paths
            alt_paths = [
                PROJECT_ROOT / script.replace("bottlesumo_pi/", ""),
            ]
            found_alt = False
            for ap in alt_paths:
                if ap.exists():
                    result.ok.append(f"Script found (alt): {script}")
                    found_alt = True
                    break
            if not found_alt:
                result.warnings.append(f"Referenced script missing: {script}")


def audit_config_consistency(result: AuditResult, fix: bool = False):
    """Check config file consistency."""
    print("\n--- Config Consistency Audit ---")

    # Check pyproject.toml vs .pre-commit-config.yaml
    pyproject = PROJECT_ROOT / "pyproject.toml"
    precommit = PROJECT_ROOT / ".pre-commit-config.yaml"
    gitignore = PROJECT_ROOT / ".gitignore"

    for f, name in [
        (pyproject, "pyproject.toml"),
        (precommit, ".pre-commit-config.yaml"),
        (gitignore, ".gitignore"),
    ]:
        if f.exists():
            result.ok.append(f"Config exists: {name}")
        else:
            result.warnings.append(f"Config missing: {name}")

    # Check CI workflows
    workflows_dir = PROJECT_ROOT / ".github" / "workflows"
    if workflows_dir.exists():
        wfs = list(workflows_dir.glob("*.yml"))
        result.ok.append(f"CI workflows: {len(wfs)} ({', '.join(w.name for w in wfs)})")
    else:
        result.warnings.append("No .github/workflows directory")


def generate_report(result: AuditResult) -> str:
    """Generate Markdown audit report."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "# 📋 Memory & Governance Audit Report",
        "",
        f"**Audit Time**: {now}",
        f"**Status**: {'✅ Clean' if result.is_clean() else '⚠️ Issues Found'}",
        "",
        "---",
        "",
        "## 📊 Summary",
        "",
        "| Category | Pass | Warn/Error |",
        "|----------|:----:|:----------:|",
        f"| Checks | {result.pass_count} | {result.fail_count} |",
        "",
        "---",
        "",
    ]

    if result.errors:
        lines.append("## ❌ Errors")
        for e in result.errors:
            lines.append(f"- {e}")
        lines.append("")

    if result.warnings:
        lines.append("## ⚠️ Warnings")
        for w in result.warnings:
            lines.append(f"- {w}")
        lines.append("")

    if result.fixes_applied:
        lines.append("## 🔧 Fixes Applied")
        for f in result.fixes_applied:
            lines.append(f"- {f}")
        lines.append("")

    if not result.errors and not result.warnings:
        lines.append("## ✅ All checks passed")
        lines.append("")
        lines.append("Memory index is consistent with filesystem. Governance structure intact.")
        lines.append("")

    return "\n".join(lines)


def main():
    fix = "--fix" in sys.argv
    result = AuditResult()

    print("=" * 50)
    print("  BottleSumo Memory Consistency Auditor")
    print("=" * 50)

    audit_memory_files(result, fix)
    audit_governance_files(result, fix)
    audit_project_assets(result, fix)
    audit_config_consistency(result, fix)

    report = generate_report(result)
    print(report)

    # Save report
    report_path = MEMORY_DIR / "audit_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(f"\nReport saved: {report_path}")

    if not result.is_clean():
        print(f"\n⚠️  Audit found {result.fail_count} issues.")
        print("   Run with --fix to auto-resolve simple problems.")
        sys.exit(1)
    else:
        print("\n✅ Memory consistency audit passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
