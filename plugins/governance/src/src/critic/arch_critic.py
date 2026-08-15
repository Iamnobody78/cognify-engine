"""Critic-Arch — 架构批判者.

职责（协议 §第三部分）:
  R1 README 宣称能力与 src/ 代码实现一致（端点宣称 → 路由表）—— HIGH
  R2 README 铁律引用的工具/脚本存在 —— MEDIUM
  R3 新依赖合理（requirements 中依赖被 src/tests import）—— LOW

对抗性: 文档里的"能力"如果没有可执行证据，就是宣称-证据断层。
"""

from __future__ import annotations

import re
from pathlib import Path

# README API 区宣称的端点 → main.py 路由表中必须存在
EXPECTED_ENDPOINTS = [
    ("POST /v1/intercept", r'add_post\("/v1/intercept"'),
    ("POST /v1/chat/completions", r'add_post\("/v1/chat/completions"'),
    ("GET /v1/health", r'add_get\("/v1/health"'),
    ("GET /v1/decisions", r'add_get\("/v1/decisions"'),
    ("GET /v1/trace/{trace_id}", r'add_get\("/v1/trace/\{trace_id\}"'),
]

# README 铁律 → 必须存在的脚本/机制
IRON_RULES = [
    ("策略必须 YAML", "scripts/check_policy.py"),
    ("测试质量门禁", "scripts/check_test_quality.py"),
    ("策略一致性门禁", "scripts/policy_sync.py"),
]


def run(repo_root: Path) -> dict:
    findings: list[dict] = []
    _check_readme_endpoints(repo_root, findings)
    _check_iron_rules_tools(repo_root, findings)
    _check_dependencies(repo_root, findings)
    return {"critic": "arch", "findings": findings}


def _finding(severity, check, evidence, suggestion) -> dict:
    return {"severity": severity, "check": check, "evidence": evidence,
            "suggestion": suggestion}


def _check_readme_endpoints(repo_root: Path, findings: list[dict]) -> None:
    readme = repo_root / "README.md"
    main_py = repo_root / "src" / "main.py"
    if not readme.exists() or not main_py.exists():
        findings.append(_finding("HIGH", "R1: README 或 main.py 缺失",
                                 "无法对比宣称与实现", "检查仓库完整性"))
        return
    readme_text = readme.read_text(encoding="utf-8")
    main_text = main_py.read_text(encoding="utf-8")
    if "/v1/intercept" not in readme_text:
        return  # README 未宣称 API → 无断言可做（但架构文档缺失应提示）
    for label, route_re in EXPECTED_ENDPOINTS:
        if not re.search(route_re, main_text):
            findings.append(_finding(
                "HIGH", "R1: 宣称端点未实现",
                f"README 宣称 {label}，但 main.py 路由表无对应 add_*",
                "实现端点或从 README 移除宣称"))


def _check_iron_rules_tools(repo_root: Path, findings: list[dict]) -> None:
    """R2: README 提到的铁律机制必须真实存在。"""
    readme = repo_root / "README.md"
    if not readme.exists():
        return
    readme_text = readme.read_text(encoding="utf-8")
    for rule, tool_rel in IRON_RULES:
        if rule in readme_text and not (repo_root / tool_rel).exists():
            findings.append(_finding(
                "MEDIUM", "R2: 铁律工具缺失",
                f"README 宣称「{rule}」但 {tool_rel} 不存在",
                "实现工具或修正 README 宣称"))


def _check_dependencies(repo_root: Path, findings: list[dict]) -> None:
    """R3: requirements 中每个依赖应在 src/ 或 tests/ 中被 import。"""
    req = repo_root / "requirements.txt"
    if not req.exists():
        return
    src_tests = ""
    for d in ("src", "tests"):
        base = repo_root / d
        if base.exists():
            src_tests += "\n".join(p.read_text(encoding="utf-8", errors="ignore")
                                   for p in base.rglob("*.py"))
    for line in req.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        pkg = line.split("==")[0].strip().replace("-", "_")
        # 包名出现于 import 或引用（宽松：字符串出现即视为引用）
        if pkg.lower() not in src_tests.lower():
            findings.append(_finding(
                "LOW", "R3: 依赖未被引用",
                f"requirements.txt: {line} 未在 src/tests 中出现 import",
                "确认依赖必要性或移除"))


def aggregate_severity(findings: list[dict]) -> str:
    if not findings:
        return "PASS"
    return max(f["severity"] for f in findings)
