#!/usr/bin/env python3
"""
BottleSumo Tool Version Manager
--------------------------------
Phase 1: Scan → Phase 2: Assess → Phase 3: Decide → Phase 4: Execute

Part of BottleSumo 140GB Flagship Edition Governance.
Integrated with .aionui/thermodynamics/entropy.log
"""

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MEMORY_DIR = PROJECT_ROOT / "memory"
ENTROPY_LOG = PROJECT_ROOT / ".aionui" / "thermodynamics" / "entropy.log"
TOOLS_REGISTRY = PROJECT_ROOT / ".aionui" / "tools" / "installed.md"

# Force UTF-8 output on Windows
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


class Severity:
    OK = "✅"
    MINOR = "🟡"
    MAJOR = "🟠"
    CRITICAL = "🔴"
    SECURITY = "⚠️"


RULE_ENGINE = {
    # (age_months, version_gap) → (severity, auto_update)
    # Age < 6 months
    (0, "patch"): (Severity.OK, True),
    (0, "minor"): (Severity.OK, True),
    (0, "major"): (Severity.MINOR, False),
    # Age 6-12 months
    (6, "patch"): (Severity.MINOR, True),
    (6, "minor"): (Severity.MAJOR, False),
    (6, "major"): (Severity.CRITICAL, False),
    # Age > 12 months
    (12, "patch"): (Severity.MAJOR, True),
    (12, "minor"): (Severity.CRITICAL, False),
    (12, "major"): (Severity.CRITICAL, False),
}


def run(cmd: list[str], shell: bool = False, timeout: int = 60) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=shell)
        return (result.stdout + result.stderr).strip()
    except Exception as e:
        return f"ERROR: {e}"


class ToolRegistry:
    """Registry of all tools in the BottleSumo toolchain."""

    def __init__(self):
        self.tools: list[dict[str, Any]] = []

    def add(
        self,
        name: str,
        category: str,
        current_version: str,
        latest_version: str = "",
        check_cmd: str = "",
        install_date: str = "",
        critical: bool = False,
    ):
        self.tools.append(
            {
                "name": name,
                "category": category,
                "current_version": current_version,
                "latest_version": latest_version,
                "check_cmd": check_cmd,
                "install_date": install_date or datetime.now(timezone.utc).isoformat()[:10],
                "critical": critical,
            }
        )

    def scan(self):
        """Phase 1: Scan all tools for current versions."""
        print("=" * 60)
        print("  Phase 1: Scanning tool versions...")
        print("=" * 60)

        # WSL tools
        def wsl(cmd):
            return run(["wsl", "bash", "-c", cmd])

        # Python ecosystem (WSL)
        py_ver = wsl("python3 --version 2>&1").replace("Python ", "")
        self.add("Python (WSL)", "runtime", py_ver, check_cmd="python3 --version")

        pip_ver = wsl("pip3 --version 2>&1").split()[1]
        self.add(
            "pip (WSL)",
            "package-manager",
            pip_ver,
            latest_version="26.2",
            check_cmd="pip3 --version",
            critical=True,
        )

        # Firmware toolchain
        gcc_out = wsl("arm-none-eabi-gcc --version 2>&1")
        gcc_parts = gcc_out.split("\n")[0].split()
        # Format: "arm-none-eabi-gcc (15:10.3.rel1) 10.3.1 20210621 (release)"
        # Version is the 4th token (index 3)
        gcc_ver_full = gcc_parts[3] if len(gcc_parts) >= 4 else "unknown"
        self.add(
            "ARM GCC",
            "firmware",
            gcc_ver_full,
            latest_version="14.2.1",
            check_cmd="arm-none-eabi-gcc --version",
            install_date="2021-07-01",
            critical=True,
        )

        # Simulation
        renode_out = wsl("renode --version 2>&1")
        renode_ver = ""
        for line in renode_out.split("\n"):
            if line.startswith("Renode v"):
                renode_ver = line.split("Renode v")[1].split()[0]
                break
        self.add("Renode", "simulation", renode_ver, check_cmd="renode --version")

        # Build system
        cmake_out = wsl("cmake --version 2>&1").split("\n")[0]
        cmake_ver = cmake_out.replace("cmake version ", "") if "cmake" in cmake_out else "not found"
        self.add("CMake (WSL)", "build", cmake_ver, check_cmd="cmake --version")

        pio_out = wsl("pip3 show platformio 2>&1")
        pio_ver = "not installed"
        for line in pio_out.split("\n"):
            if line.startswith("Version:"):
                pio_ver = line.split(":")[1].strip()
        self.add("PlatformIO", "firmware", pio_ver, check_cmd="pip3 show platformio")

        # Testing
        pytest_out = wsl("pip3 show pytest 2>&1")
        pytest_ver = "not installed"
        for line in pytest_out.split("\n"):
            if line.startswith("Version:"):
                pytest_ver = line.split(":")[1].strip()
        self.add(
            "pytest (WSL)",
            "testing",
            pytest_ver,
            latest_version="9.1.1",
            check_cmd="pip3 show pytest",
        )

        # Windows tools
        self.add("Python (Win)", "runtime", "3.12.10", check_cmd="python --version")
        self.add("Git (Win)", "vcs", "2.55.0", check_cmd="git --version")
        self.add(
            "pip (Win)",
            "package-manager",
            "26.1.2",
            latest_version="26.2",
            check_cmd="pip --version",
        )

        ruff_out = run(["pip", "show", "ruff"])
        ruff_ver = "not installed"
        for line in ruff_out.split("\n"):
            if line.startswith("Version:"):
                ruff_ver = line.split(":")[1].strip()
        self.add("ruff", "linter", ruff_ver, check_cmd="pip show ruff")

        precommit_out = run(["pip", "show", "pre-commit"])
        pc_ver = "not installed"
        for line in precommit_out.split("\n"):
            if line.startswith("Version:"):
                pc_ver = line.split(":")[1].strip()
        self.add("pre-commit", "hooks", pc_ver, check_cmd="pip show pre-commit")

        # Missing tools (tracked as debt)
        for tool, cat in [("OpenOCD", "firmware"), ("ROS2", "simulation")]:
            self.add(
                tool,
                cat,
                "MISSING",
                check_cmd=f"which {tool.lower()}",
                critical=(tool == "OpenOCD"),
            )

        print(f"  Scanned {len(self.tools)} tools.\n")
        return self.tools

    def assess(self):
        """Phase 2: Assess update urgency and risk."""
        print("=" * 60)
        print("  Phase 2: Assessing version gaps...")
        print("=" * 60)

        findings = {
            "ok": [],
            "minor": [],
            "major": [],
            "critical": [],
            "security": [],
            "missing": [],
        }

        for t in self.tools:
            if t["current_version"] == "MISSING":
                findings["missing"].append(t)
                continue

            cur = t["current_version"]
            latest = t.get("latest_version", cur)

            # Parse versions
            cur_parts = _parse_version(cur)
            latest_parts = _parse_version(latest)

            if not cur_parts or not latest_parts or latest_parts == cur_parts:
                findings["ok"].append(t)
                continue

            # Determine gap type
            gap = _version_gap(cur_parts, latest_parts)
            age = _age_months(t.get("install_date", ""))

            _severity, auto = Severity.OK, True
            for (age_thresh, gap_type), (sev, aut) in RULE_ENGINE.items():
                if age >= age_thresh and gap == gap_type or age >= age_thresh and gap == "minor" and gap_type == "patch":
                    _severity, auto = sev, aut

            t["gap_type"] = gap
            t["age_months"] = age
            t["auto_update"] = auto

            if gap == "major":
                findings["major"].append(t)
            elif age >= 12:
                findings["critical"].append(t)
            elif gap == "minor" and not auto:
                findings["major"].append(t)
            else:
                findings["minor"].append(t)

        print(f"  ✅ Up-to-date:  {len(findings['ok'])}")
        print(f"  🟡 Minor:        {len(findings['minor'])}")
        print(f"  🟠 Major:        {len(findings['major'])}")
        print(f"  🔴 Critical:     {len(findings['critical'])}")
        print(f"  ⚠️  Security:     {len(findings['security'])}")
        print(f"  ❌ Missing:      {len(findings['missing'])}")
        print()
        return findings

    def decide(self, findings):
        """Phase 3: Decide which updates to apply."""
        print("=" * 60)
        print("  Phase 3: Update decisions...")
        print("=" * 60)

        decisions = {"auto": [], "confirm": [], "blocked": []}

        for category, tools in findings.items():
            for t in tools:
                if category == "ok":
                    continue
                if category == "missing" or category == "critical":
                    decisions["confirm"].append(t)
                elif t.get("auto_update", False):
                    decisions["auto"].append(t)
                else:
                    decisions["confirm"].append(t)

        print(f"  🤖 Auto-update:   {len(decisions['auto'])}")
        print(f"  ✋ Needs confirm: {len(decisions['confirm'])}")
        print(f"  🚫 Blocked:       {len(decisions['blocked'])}")
        print()
        return decisions

    def execute(self, decisions, dry_run=True):
        """Phase 4: Execute updates."""
        print("=" * 60)
        print(f"  Phase 4: Executing updates {'(DRY RUN)' if dry_run else '(LIVE)'}...")
        print("=" * 60)

        results = []

        for t in decisions.get("auto", []):
            name = t["name"]
            cmd = self._update_command(t)
            if dry_run:
                print(f"  [DRY RUN] Would update {name}: {cmd}")
                results.append((name, "DRY_RUN", cmd))
            else:
                print(f"  Updating {name}...")
                out = run(cmd.split() if not isinstance(cmd, list) else cmd, timeout=120)
                success = "ERROR" not in out
                results.append((name, "OK" if success else "FAIL", cmd))
                print(f"    → {'OK' if success else 'FAILED'}")

        for t in decisions.get("confirm", []):
            name = t["name"]
            print(
                f"  ⏸️  SKIPPED (needs confirmation): {name} "
                f"({t.get('current_version', '?')} → {t.get('latest_version', '?')})"
            )

        return results

    def _update_command(self, tool):
        """Generate update command for a tool."""
        name = tool["name"].lower()
        cat = tool["category"]

        if "pip" in name and "wsl" in name.lower():
            return "wsl pip3 install --upgrade pip"
        if "pip" in name:
            return "python -m pip install --upgrade pip"
        if cat == "linter" or cat == "hooks" or cat == "testing":
            return f"pip install --upgrade {tool['name']}"

        return f"# Manual update required for {tool['name']}"

    def generate_report(self, findings, decisions, results) -> str:
        """Generate Markdown report."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        lines = [
            "# 🔍 工具版本检测报告",
            "",
            f"**扫描时间**: {now}",
            f"**扫描范围**: {len(self.tools)} 个工具",
            "",
            "---",
            "",
            "## 📊 概览",
            "",
            "| 状态 | 数量 | 说明 |",
            "|------|:----:|------|",
            f"| ✅ 最新 | {len(findings['ok'])} | 已是最新版本 |",
            f"| 🟡 可更新 | {len(findings['minor'])} | 有更新可用(自动) |",
            f"| 🟠 需确认 | {len(findings['major'])} | Major版本变更 |",
            f"| 🔴 严重过时 | {len(findings['critical'])} | 超过12个月 |",
            f"| ❌ 缺失 | {len(findings['missing'])} | 未安装的工具 |",
            "",
            "---",
            "",
        ]

        # Critical tools
        if findings["critical"]:
            lines.append("## 🔴 严重过时工具")
            lines.append("")
            lines.append("| 工具 | 当前版本 | 最新版本 | 年龄 | 风险 |")
            lines.append("|------|----------|----------|------|------|")
            for t in findings["critical"]:
                lines.append(
                    f"| {t['name']} | {t['current_version']} | "
                    f"{t.get('latest_version', '?')} | "
                    f"{t.get('age_months', '?')}月 | 安全漏洞+功能落后 |"
                )
            lines.append("")

        # Missing tools
        if findings["missing"]:
            lines.append("## ❌ 缺失工具")
            lines.append("")
            lines.append("| 工具 | 类别 | 影响 |")
            lines.append("|------|------|------|")
            for t in findings["missing"]:
                impact = {
                    "OpenOCD": "无法烧录/调试物理STM32硬件",
                    "ROS2": "Gazebo仿真集成依赖",
                }.get(t["name"], "未知")
                lines.append(f"| {t['name']} | {t['category']} | {impact} |")
            lines.append("")

        # Auto-update candidates
        if decisions.get("auto"):
            lines.append("## 🤖 自动更新候选")
            lines.append("")
            lines.append("| 工具 | 版本变更 | 类型 |")
            lines.append("|------|----------|------|")
            for t in decisions["auto"]:
                lines.append(
                    f"| {t['name']} | {t['current_version']} → "
                    f"{t.get('latest_version', '?')} | {t.get('gap_type', '?')} |"
                )
            lines.append("")

        # Need confirmation
        if decisions.get("confirm"):
            lines.append("## ✋ 需确认的更新")
            lines.append("")
            lines.append("| 工具 | 版本变更 | 类型 | 风险 |")
            lines.append("|------|----------|------|------|")
            for t in decisions["confirm"]:
                risk = "API breaking changes" if t.get("gap_type") == "major" else "长期未更新"
                lines.append(
                    f"| {t['name']} | {t['current_version']} → "
                    f"{t.get('latest_version', '?')} | {t.get('gap_type', '?')} | {risk} |"
                )
            lines.append("")

        # Results
        if results:
            lines.append("## ⚡ 执行结果")
            lines.append("")
            lines.append("| 工具 | 状态 | 命令 |")
            lines.append("|------|:----:|------|")
            for name, status, cmd in results:
                lines.append(f"| {name} | {status} | `{cmd}` |")
            lines.append("")

        return "\n".join(lines)


def _parse_version(v: str) -> tuple | None:
    """Parse version string to comparable tuple."""
    import re

    parts = re.findall(r"(\d+)", v)
    if not parts:
        return None
    return tuple(int(p) for p in parts[:4])


def _version_gap(cur: tuple, latest: tuple) -> str:
    """Determine if gap is patch, minor, or major."""
    if not cur or not latest:
        return "unknown"
    for i in range(min(len(cur), len(latest))):
        if latest[i] > cur[i]:
            if i == 0:
                return "major"
            elif i == 1:
                return "minor"
            else:
                return "patch"
    return "unknown"


def _age_months(date_str: str) -> int:
    """Calculate age in months from install date."""
    if not date_str:
        return 24  # Unknown age → assume old
    try:
        install = datetime.strptime(date_str, "%Y-%m-%d")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        delta = now - install
        return delta.days // 30
    except Exception:
        return 24


def main(dry_run=True):
    registry = ToolRegistry()
    registry.scan()
    findings = registry.assess()
    decisions = registry.decide(findings)
    results = registry.execute(decisions, dry_run=dry_run)
    report = registry.generate_report(findings, decisions, results)
    return report, registry, findings, decisions, results


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv or "--auto" not in sys.argv
    report, *_ = main(dry_run=dry)
    print(report)
    # Save report
    out_path = MEMORY_DIR / "tool_version_report.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"\nReport saved to {out_path}")
