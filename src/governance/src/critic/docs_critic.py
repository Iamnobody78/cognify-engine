"""Critic-Docs — 文档批判者.

职责（协议 §第三部分）:
  D1 文档中每个 tests/xxx.py / src/xxx.py / docs/xxx.md 引用存在 —— MEDIUM
  D2 README 版本声明与 main.py 版本常量一致 —— MEDIUM
  D3 README 铁律与 CI 实际执行一致 —— HIGH

对抗性: 文档中的"宣称"必须在源码/工具链中找到对应证据。
"""

from __future__ import annotations

import re
from pathlib import Path

REF_RE = re.compile(r"(?:tests|src|scripts|docs)/[\w./\-]+\.(?:py|md|yaml|yml|txt)")  # noqa: policy (technical ref parser)
# 批判者 v1.0.1 修正（自记录）: 原 VERSION_RE 要求 'v' 前缀，main.py 的
# 裸版本常量（如 "0.4.0"）被漏检 → 真实仓库版本一致性从未被检查。
VERSION_RE = re.compile(r"v?(\d+\.\d+\.\d+)")  # noqa: policy (technical version parser)


def run(repo_root: Path) -> dict:
    findings: list[dict] = []
    md_files = _collect_markdown(repo_root)
    _check_file_references(repo_root, md_files, findings)
    _check_version_consistency(repo_root, findings)
    _check_iron_rules_ci(repo_root, findings)
    return {"critic": "docs", "findings": findings}


def _finding(severity, check, evidence, suggestion) -> dict:
    return {"severity": severity, "check": check, "evidence": evidence,
            "suggestion": suggestion}


def _collect_markdown(repo_root: Path) -> list[Path]:
    files = []
    for d in ("", "docs", ".aionui", ".aionui/context", ".aionui/protocols"):
        base = repo_root / d
        if base.exists():
            files.extend(base.glob("*.md"))
    # 批判者 v1.0.1 修正（自记录）: 排除批判报告自身 —— 报告含模板占位符
    # 示例（tests/xxx.py 等），会被 D1 误判为文档-代码断层（自引用误报）。
    return [f for f in sorted(files) if f.name != "critic_report.md"]


def _check_file_references(repo_root: Path, md_files: list[Path],
                           findings: list[dict]) -> None:
    """D1: md 中引用的相对路径文件必须存在。"""
    for mdf in md_files:
        text = mdf.read_text(encoding="utf-8", errors="ignore")
        for m in REF_RE.finditer(text):
            ref = m.group(0).strip("`").strip()
            # 跳过占位符/伪引用（{xxx}、模板示例、markdown 链接目标片段）
            if "{" in ref or "(" in ref or ")" in ref or "xxx" in ref or "XXX" in ref:
                continue
            if not (repo_root / ref).exists():
                findings.append(_finding(
                    "MEDIUM", "D1: 文档引用文件不存在",
                    f"{mdf.relative_to(repo_root)}: 引用 `{ref}` 但文件不存在",
                    "创建文件或修正文档引用（文档-代码断层）"))


def _check_version_consistency(repo_root: Path, findings: list[dict]) -> None:
    """D2: README 最新版本声明 == main.py 版本常量。"""
    readme = repo_root / "README.md"
    main_py = repo_root / "src" / "main.py"
    if not readme.exists() or not main_py.exists():
        return
    readme_text = readme.read_text(encoding="utf-8")
    main_text = main_py.read_text(encoding="utf-8")
    readme_versions = set(VERSION_RE.findall(readme_text))
    main_versions = set(VERSION_RE.findall(main_text))
    if readme_versions and main_versions:
        # main.py 最新版本必须出现在 README
        newest_main = max(main_versions, key=lambda v: tuple(int(x) for x in v.split(".")))
        if newest_main not in readme_versions:
            findings.append(_finding(
                "MEDIUM", "D2: 版本声明不一致",
                f"main.py 版本 {newest_main} 未出现在 README 版本声明中",
                "README 补版本变更记录（宣称-文档断层）"))


def _check_iron_rules_ci(repo_root: Path, findings: list[dict]) -> None:
    """D3: README 铁律（门禁/GATE 宣称）对应 CI job 存在。"""
    readme = repo_root / "README.md"
    ci = repo_root / ".github" / "workflows" / "ci.yml"
    if not readme.exists() or not ci.exists():
        return
    readme_text = readme.read_text(encoding="utf-8")
    ci_text = ci.read_text(encoding="utf-8")
    gate_claims = re.findall(r"GATE\s*(\d+)", readme_text, re.IGNORECASE)
    if not gate_claims:
        return
    for g in gate_claims:
        if f"Gate {g}" not in ci_text and f"GATE {g}" not in ci_text.upper():
            findings.append(_finding(
                "HIGH", "D3: 铁律与 CI 不一致",
                f"README 宣称 GATE {g}，ci.yml 无对应 job/步骤",
                "补齐 CI 门禁或修正 README 宣称"))


def aggregate_severity(findings: list[dict]) -> str:
    if not findings:
        return "PASS"
    return max(f["severity"] for f in findings)
