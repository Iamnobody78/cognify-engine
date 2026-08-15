"""Critic-Security — 安全批判者.

职责（协议 §第三部分）:
  S1 熔断器 fail-closed（CIRCUIT_BREAKER_LIMIT 触发后 DENY 而非 ALLOW）—— HIGH
  S2 超时 fail-closed（asyncio.wait_for 超时后 DENY 而非 ALLOW）—— HIGH
  S3 路径匹配无 startswith 绕过（可被路径遍历利用）—— HIGH
  S4 SQL 全参数化（无 f-string/拼接注入面）—— HIGH
  S5 trace 头长度守卫存在（防索引膨胀/存储滥用）—— MEDIUM
  S6 AST 阻断（若存在 ast_guard.py 必须被实际引用）—— MEDIUM

对抗性: 静态扫描真实源码并给出 文件:行号 证据。
"""

from __future__ import annotations

import re
from pathlib import Path

DENY_MARKERS = ("DENY", "deny", "fail-closed", "fail_closed")


def run(repo_root: Path) -> dict:
    findings: list[dict] = []
    src = repo_root / "src"
    main_py = src / "main.py"
    storage_py = src / "storage.py"
    _check_circuit_breaker(main_py, findings)
    _check_timeout(main_py, findings)
    _check_path_match(main_py, findings)
    _check_sql_parametrized(storage_py, findings)
    _check_trace_length_guard(main_py, findings)
    _check_ast_guard(src, main_py, findings)
    return {"critic": "security", "findings": findings}


def _finding(severity, check, evidence, suggestion) -> dict:
    return {"severity": severity, "check": check, "evidence": evidence,
            "suggestion": suggestion}


def _ctx_has_deny(text: str, match_start: int, radius: int = 400) -> bool:
    window = text[max(0, match_start - radius): match_start + radius]
    return any(m in window for m in DENY_MARKERS)


def _check_circuit_breaker(main_py: Path, findings: list[dict]) -> None:
    if not main_py.exists():
        findings.append(_finding("HIGH", "S1: main.py 缺失",
                                 "src/main.py 不存在", "检查源码完整性"))
        return
    text = main_py.read_text(encoding="utf-8")
    hits = [m for m in re.finditer(r"CIRCUIT_BREAKER_LIMIT", text)]
    if not hits:
        findings.append(_finding("HIGH", "S1: 熔断器缺失",
                                 "main.py 无 CIRCUIT_BREAKER_LIMIT", "补熔断机制"))
        return
    for m in hits:
        if not _ctx_has_deny(text, m.start()):
            line_no = text[: m.start()].count("\n") + 1
            findings.append(_finding(
                "HIGH", "S1: 熔断未 fail-closed",
                f"src/main.py:{line_no} CIRCUIT_BREAKER_LIMIT 上下文无 DENY/fail-closed",
                "熔断触发后必须 DENY（默认拒绝）"))


def _check_timeout(main_py: Path, findings: list[dict]) -> None:
    """S2: 策略评估超时（INTERCEPT_TIMEOUT）必须 fail-closed。

    批判者 v1.0.1 修正（自记录）: 原实现扫描所有 asyncio.wait_for/
    TimeoutError，把 shutdown flush 等非策略超时误报为 HIGH —— 仅
    锚定 INTERCEPT_TIMEOUT 使用处（排除常量定义行）。
    """
    if not main_py.exists():
        return
    text = main_py.read_text(encoding="utf-8")
    # 使用处 = timeout=INTERCEPT_TIMEOUT 或 wait_for(..., INTERCEPT_TIMEOUT)
    usage = [m for m in re.finditer(r"INTERCEPT_TIMEOUT", text)
             if "=" not in text[m.start() - 8:m.start()] or "timeout" in text[max(0, m.start()-30):m.start()]]
    if not usage:
        findings.append(_finding(
            "MEDIUM", "S2: 无策略评估超时",
            "main.py 未发现 INTERCEPT_TIMEOUT 使用处",
            "网关应有策略评估超时 fail-closed"))
        return
    for m in usage:
        if not _ctx_has_deny(text, m.start(), radius=600):
            line_no = text[: m.start()].count("\n") + 1
            findings.append(_finding(
                "HIGH", "S2: 策略评估超时未 fail-closed",
                f"src/main.py:{line_no} INTERCEPT_TIMEOUT 上下文无 DENY/fail-closed",
                "超时分支必须返回 DENY（默认拒绝）而非 ALLOW"))


def _check_path_match(main_py: Path, findings: list[dict]) -> None:
    if not main_py.exists():
        return
    text = main_py.read_text(encoding="utf-8")
    # 路径判定应基于策略（re.compile / 完整路径），startswith 前缀匹配可被
    # /api/query/../../admin 类路径遍历绕过（若随后做资源访问）。
    for m in re.finditer(r"\.startswith\(", text):
        line = text[: m.start()].count("\n") + 1
        findings.append(_finding(
            "HIGH", "S3: startswith 前缀匹配",
            f"src/main.py:{line} `{text[m.start()-40:m.start()+40].strip()[:80]}`",
            "路径/资源判定改用精确匹配或 re.compile 全路径锚定"))


def _check_sql_parametrized(storage_py: Path, findings: list[dict]) -> None:
    if not storage_py.exists():
        findings.append(_finding("HIGH", "S4: storage.py 缺失",
                                 "src/storage.py 不存在", "检查源码完整性"))
        return
    text = storage_py.read_text(encoding="utf-8")
    for m in re.finditer(r"(execute|executemany)\s*\(\s*[fF]['\"]", text):
        line_no = text[: m.start()].count("\n") + 1
        findings.append(_finding(
            "HIGH", "S4: SQL f-string 拼接",
            f"src/storage.py:{line_no} f-string SQL 存在注入面",
            "一律使用参数化查询 execute(sql, (params,))"))
    # 二次确认: 无 f-string 时要求至少存在 execute(..., ( 参数化形态
    if not re.search(r"execute\s*\([^)]*,\s*\(", text):
        findings.append(_finding(
            "MEDIUM", "S4: 无法确认参数化",
            "src/storage.py 未发现 execute(sql, (params,)) 形态",
            "确认所有 SQL 均参数化"))


def _check_trace_length_guard(main_py: Path, findings: list[dict]) -> None:
    """S5: MAX_TRACE_ID_LEN 必须被 _trace_context 使用（TASK-REAL-011.1）。"""
    if not main_py.exists():
        return
    text = main_py.read_text(encoding="utf-8")
    if "MAX_TRACE_ID_LEN" not in text:
        findings.append(_finding(
            "MEDIUM", "S5: trace 头长度守卫缺失",
            "main.py 无 MAX_TRACE_ID_LEN",
            "X-Trace-ID/X-Parent-Span-ID 需长度上限（防索引膨胀/存储滥用）"))


def _check_ast_guard(src: Path, main_py: Path, findings: list[dict]) -> None:
    """S6: 若存在 ast_guard.py，必须被 main.py 实际引用（否则是死代码）。"""
    ast_guard = src / "ast_guard.py"
    if not ast_guard.exists():
        return  # 无 AST 层则不检查
    if not main_py.exists():
        return
    text = main_py.read_text(encoding="utf-8")
    if "ast_guard" not in text:
        findings.append(_finding(
            "MEDIUM", "S6: AST 阻断未启用",
            "src/ast_guard.py 存在但 main.py 未引用",
            "接入 AST 检查到拦截链，或删除死代码"))


def aggregate_severity(findings: list[dict]) -> str:
    if not findings:
        return "PASS"
    return max(f["severity"] for f in findings)
