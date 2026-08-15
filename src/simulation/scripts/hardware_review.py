#!/usr/bin/env python3
"""
BottleSumo Hardware Review Script
----------------------------------
Scans KiCad projects (.kicad_sch, .kicad_pcb), STL/STEP models, and generates
a structured review report. Works in CI (headless) and local dev environments.

Usage:
  python hardware_review.py --scan-root hardware/ --output review_report.md
  python hardware_review.py --check-ctea  # CTEA competition compliance check
"""

import argparse
import contextlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Force UTF-8 on Windows
with contextlib.suppress(Exception):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MEMORY_DIR = PROJECT_ROOT / "memory"

# CTEA Competition Rules (20th Senior Division)
CTEA_RULES = {
    "max_size_mm": [150, 150, 150],  # L x W x H (estimate)
    "max_weight_g": 500,
    "voltage_max_v": 3.0,  # Overcurrent protection
    "wheels_min": 2,
    "wheels_max": 4,
    "battery_type": "Li-Po 2S (7.4V nominal)",
    "start_delay_s": 5,
    "stop_after_s": 180,
}


def scan_kicad_projects(root: str) -> list[dict[str, Any]]:
    """Find all KiCad project directories and their assets."""
    projects = []
    seen_dirs = set()

    for ext in [".kicad_sch", ".kicad_pcb", ".kicad_pro"]:
        for f in Path(root).rglob(f"*{ext}"):
            if "~" in f.name or ".lck" in f.suffix:
                continue
            proj_dir = str(f.parent)
            if proj_dir not in seen_dirs:
                seen_dirs.add(proj_dir)
                proj_info = {"path": proj_dir, "schematics": [], "pcbs": [], "kicad_pro": None}
                projects.append(proj_info)

    for p in projects:
        pd = Path(p["path"])
        p["schematics"] = sorted([str(f.name) for f in pd.glob("*.kicad_sch") if "~" not in f.name])
        p["pcbs"] = sorted([str(f.name) for f in pd.glob("*.kicad_pcb") if "~" not in f.name])
        pro_files = list(pd.glob("*.kicad_pro"))
        if pro_files:
            p["kicad_pro"] = str(pro_files[0].name)

    return projects


def analyze_schematic(sch_path: str) -> dict[str, Any]:
    """Extract metadata from KiCad schematic (S-expression parse)."""
    info = {"path": sch_path, "errors": [], "warnings": [], "stats": {}}

    try:
        with open(sch_path, encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        info["errors"].append(f"Cannot read: {e}")
        return info

    # Count symbols (components)
    symbols = re.findall(r"\(symbol\s", content)
    info["stats"]["component_count"] = len(symbols)

    # Count wires
    wires = re.findall(r"\(wire\s", content)
    info["stats"]["wire_count"] = len(wires)

    # Check for unconnected nets
    unconnected = re.findall(r"\(no_connect\s", content)
    if unconnected:
        info["warnings"].append(f"{len(unconnected)} unconnected pins (no-connect flags)")

    # Check for power symbols
    power_symbols = re.findall(r'\(property\s+"Reference"\s"#PWR', content)
    info["stats"]["power_symbols"] = len(power_symbols)

    # Check for STM32 MCU
    if "STM32" in content or "stm32" in content.lower():
        mcu_matches = re.findall(r"STM32\w+", content)
        info["stats"]["mcu"] = list(set(mcu_matches))

    return info


def analyze_pcb(pcb_path: str) -> dict[str, Any]:
    """Extract metadata from KiCad PCB (S-expression parse)."""
    info = {"path": pcb_path, "errors": [], "warnings": [], "stats": {}}

    try:
        with open(pcb_path, encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        info["errors"].append(f"Cannot read: {e}")
        return info

    # Count footprints
    footprints = re.findall(r"\(footprint\s", content)
    info["stats"]["footprint_count"] = len(footprints)

    # Count vias
    vias = re.findall(r"\(via\s", content)
    info["stats"]["via_count"] = len(vias)

    # Count tracks
    tracks = re.findall(r"\(segment\s", content)
    info["stats"]["track_count"] = len(tracks)

    # Detect board outline
    if "Edge.Cuts" in content:
        info["stats"]["has_board_outline"] = True
    else:
        info["warnings"].append("No Edge.Cuts layer defined (board outline missing)")

    # Estimate board size (very rough)
    board_size = re.findall(r"\(gr_line\s.*?\)", content, re.DOTALL)
    info["stats"]["board_outline_segments"] = len(board_size)

    # Check layer count
    layer_count = len(set(re.findall(r'"([^"]+\.Cu)"', content)))
    info["stats"]["copper_layers"] = layer_count
    if layer_count > 2:
        info["warnings"].append(f"{layer_count} copper layers — verify if >2 is needed")

    return info


def scan_cad_models(root: str) -> dict[str, Any]:
    """Scan CAD models (STL, STEP) and check properties."""
    models = {"stl": [], "step": [], "issues": []}

    for f in Path(root).rglob("*.stl"):
        try:
            size = f.stat().st_size
            models["stl"].append(
                {"name": str(f.relative_to(root)), "size_bytes": size, "size_mb": size / 1e6}
            )
            if size > 50_000_000:  # 50MB
                models["issues"].append(f"Large STL: {f.name} ({size / 1e6:.1f}MB)")
        except Exception:
            pass

    for f in Path(root).rglob("*.step"):
        try:
            size = f.stat().st_size
            models["step"].append(
                {"name": str(f.relative_to(root)), "size_bytes": size, "size_mb": size / 1e6}
            )
        except Exception:
            pass

    return models


def check_ctea_compliance(projects: list[dict]) -> list[str]:
    """Check against CTEA competition rules."""
    issues = []

    for p in projects:
        pname = Path(p["path"]).name

        if p["schematics"] and p["pcbs"]:
            pass
        elif p["schematics"]:
            issues.append(f"{pname}: Schematic exists but no PCB layout")
        elif p["pcbs"]:
            issues.append(f"{pname}: PCB exists but no schematic")

        # Check key components presence
        all_files = p["schematics"] + p["pcbs"]
        if all_files:
            combined = ""
            for f in all_files:
                fpath = Path(p["path"]) / f
                if fpath.exists():
                    with contextlib.suppress(Exception):
                        combined += fpath.read_text(encoding="utf-8", errors="replace")

            if "STM32" not in combined and "stm32" not in combined.lower():
                issues.append(f"{pname}: No STM32 MCU detected in design")

    return issues


def generate_report(
    projects: list[dict],
    schematics: list[dict],
    pcbs: list[dict],
    cad_models: dict,
    ctea_issues: list[str],
) -> str:
    """Generate Markdown review report."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "# 🔌 BottleSumo Hardware Review Report",
        "",
        f"**Generated**: {now}",
        f"**Projects Found**: {len(projects)}",
        "",
        "---",
        "",
        "## 📊 Overview",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| KiCad Projects | {len(projects)} |",
        f"| Schematics | {sum(len(p['schematics']) for p in projects)} |",
        f"| PCB Layouts | {sum(len(p['pcbs']) for p in projects)} |",
        f"| STL Models | {len(cad_models.get('stl', []))} |",
        f"| STEP Models | {len(cad_models.get('step', []))} |",
        f"| CTEA Issues | {len(ctea_issues)} |",
        "",
        "---",
        "",
    ]

    # Project list
    if projects:
        lines.append("## 📁 KiCad Projects")
        lines.append("")
        lines.append("| Project | Schematics | PCBs | Components |")
        lines.append("|---------|:----------:|:----:|:----------:|")
        for p in projects:
            name = Path(p["path"]).name
            sch_count = len(p["schematics"])
            pcb_count = len(p["pcbs"])
            # Try to count components from schematic analysis
            comp_count = "?"
            for s in schematics:
                if s["path"].startswith(p["path"]):
                    comp_count = str(s["stats"].get("component_count", "?"))
                    break
            lines.append(f"| {name} | {sch_count} | {pcb_count} | {comp_count} |")
        lines.append("")

    # Schematic details
    if schematics:
        lines.append("## 🔌 Schematic Analysis")
        lines.append("")
        for s in schematics:
            name = Path(s["path"]).name
            stats = s["stats"]
            mcu = stats.get("mcu", [])
            lines.append(f"### {name}")
            lines.append(f"- Components: {stats.get('component_count', '?')}")
            lines.append(f"- Wires: {stats.get('wire_count', '?')}")
            lines.append(f"- Power symbols: {stats.get('power_symbols', '?')}")
            if mcu:
                lines.append(f"- MCU detected: {', '.join(mcu)}")
            for w in s.get("warnings", []):
                lines.append(f"- ⚠️ {w}")
            for e in s.get("errors", []):
                lines.append(f"- ❌ {e}")
            lines.append("")
        lines.append("")

    # PCB details
    if pcbs:
        lines.append("## 📐 PCB Analysis")
        lines.append("")
        for p in pcbs:
            name = Path(p["path"]).name
            stats = p["stats"]
            lines.append(f"### {name}")
            lines.append(f"- Footprints: {stats.get('footprint_count', '?')}")
            lines.append(f"- Vias: {stats.get('via_count', '?')}")
            lines.append(f"- Tracks: {stats.get('track_count', '?')}")
            lines.append(f"- Copper layers: {stats.get('copper_layers', '?')}")
            lines.append(f"- Board outline: {'Yes' if stats.get('has_board_outline') else 'No'}")
            for w in p.get("warnings", []):
                lines.append(f"- ⚠️ {w}")
            lines.append("")
        lines.append("")

    # CTEA Compliance
    if ctea_issues:
        lines.append("## 🏆 CTEA Competition Compliance")
        lines.append("")
        lines.append("| Issue |")
        lines.append("|-------|")
        for issue in ctea_issues:
            lines.append(f"| ⚠️ {issue} |")
        lines.append("")
    else:
        lines.append("## 🏆 CTEA Competition Compliance")
        lines.append("")
        lines.append("✅ All basic checks passed (ERC/DRC recommended for full compliance)")
        lines.append("")

    # CAD models
    if cad_models.get("stl") or cad_models.get("step"):
        lines.append("## 📦 CAD Models")
        lines.append("")
        if cad_models.get("stl"):
            lines.append("| STL File | Size |")
            lines.append("|----------|------|")
            for m in cad_models["stl"]:
                lines.append(f"| {m['name']} | {m['size_mb']:.1f} MB |")
            lines.append("")
        if cad_models.get("step"):
            lines.append("| STEP File | Size |")
            lines.append("|-----------|------|")
            for m in cad_models["step"]:
                lines.append(f"| {m['name']} | {m['size_mb']:.1f} MB |")
            lines.append("")
        if cad_models.get("issues"):
            lines.append("### ⚠️ Issues")
            for issue in cad_models["issues"]:
                lines.append(f"- {issue}")
            lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="BottleSumo Hardware Review Script")
    parser.add_argument("--scan-root", default=".", help="Root directory to scan")
    parser.add_argument("--output", default="hw_review_report.md", help="Output markdown file")
    parser.add_argument("--check-ctea", action="store_true", help="CTEA compliance check")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of Markdown")
    args = parser.parse_args()

    root = args.scan_root
    print(f"🔍 Scanning hardware designs in: {root}")

    # Scan
    projects = scan_kicad_projects(root)
    print(f"  Found {len(projects)} KiCad projects")

    schematics = []
    pcbs = []

    for p in projects:
        for sch in p["schematics"]:
            info = analyze_schematic(str(Path(p["path"]) / sch))
            schematics.append(info)
        for pcb in p["pcbs"]:
            info = analyze_pcb(str(Path(p["path"]) / pcb))
            pcbs.append(info)

    cad_models = scan_cad_models(root)
    ctea_issues = check_ctea_compliance(projects) if args.check_ctea else []

    # Generate report
    if args.json:
        output = json.dumps(
            {
                "projects": projects,
                "schematics": schematics,
                "pcbs": pcbs,
                "cad_models": cad_models,
                "ctea_issues": ctea_issues,
            },
            indent=2,
            default=str,
        )
    else:
        output = generate_report(projects, schematics, pcbs, cad_models, ctea_issues)

    # Save
    out_path = Path(args.output)
    out_path.write_text(output, encoding="utf-8")
    print(f"  Report saved to: {out_path}")
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
