"""Critic-Test — 测试批判者.

职责（协议 §第三部分）:
  T1 测试有真实断言（assert 行为，而非仅构造对象不抛异常）—— MEDIUM
  T2 测试有真实 IO/状态迁移断言（HTTP 客户端 / 存储交互）—— MEDIUM
  T3 覆盖率证据存在（.coverage / coverage.xml）—— LOW
  T4 新增 src 模块有对应测试文件 —— LOW

对抗性: "测试通过"不等于"行为被验证"。每个断言必须锚定行为而非仅不崩溃。
"""

from __future__ import annotations

import re
from pathlib import Path

# 判定测试是否触达真实 IO/状态迁移的启发式
IO_MARKERS = (
    "aiohttp_client", "AioHTTPTestCase", "unittest_run_loop",
    "Storage(", "storage.", "await client.post", "await client.get",
    "asyncio.to_thread", "sqlite3",
)


def run(repo_root: Path) -> dict:
    findings: list[dict] = []
    tests = repo_root / "tests"
    if not tests.exists():
        findings.append(_finding("MEDIUM", "T1: 测试目录缺失",
                                 "tests/ 不存在", "建立测试"))
        return {"critic": "test", "findings": findings}
    _check_real_assertions(tests, findings)
    _check_io_coverage(tests, findings)
    _check_coverage_artifact(repo_root, findings)
    _check_module_tests(repo_root, tests, findings)
    return {"critic": "test", "findings": findings}


def _finding(severity, check, evidence, suggestion) -> dict:
    return {"severity": severity, "check": check, "evidence": evidence,
            "suggestion": suggestion}


def _check_real_assertions(tests: Path, findings: list[dict]) -> None:
    """T1: 每个测试文件必须有 assert（非仅 import/构造）。"""
    for tf in sorted(tests.glob("test_*.py")):
        text = tf.read_text(encoding="utf-8", errors="ignore")
        assert_count = len(re.findall(r"\bassert\b", text))
        if assert_count == 0:
            findings.append(_finding(
                "MEDIUM", "T1: 测试无断言",
                f"{tf.relative_to(tests.parent)} 无 assert 语句",
                "每个测试必须验证行为"))


def _check_io_coverage(tests: Path, findings: list[dict]) -> None:
    """T2: 至少存在触达真实 IO/状态迁移的测试文件。"""
    touched = []
    for tf in sorted(tests.glob("test_*.py")):
        text = tf.read_text(encoding="utf-8", errors="ignore")
        if any(m in text for m in IO_MARKERS):
            touched.append(tf.name)
    if not touched:
        findings.append(_finding(
            "MEDIUM", "T2: 无 IO/状态迁移测试",
            "tests/ 中未发现 HTTP 客户端 / Storage / 异步交互标记",
            "补充 e2e/迁移测试（行为验证而非纯单元构造）"))


def _check_coverage_artifact(repo_root: Path, findings: list[dict]) -> None:
    """T3: 覆盖率证据存在。"""
    has_cov = (repo_root / ".coverage").exists() or (repo_root / "coverage.xml").exists()
    if not has_cov:
        findings.append(_finding(
            "LOW", "T3: 覆盖率证据缺失",
            "未找到 .coverage / coverage.xml",
            "CI 运行 pytest --cov 并保存产物"))


def _check_module_tests(repo_root: Path, tests: Path, findings: list[dict]) -> None:
    """T4: 每个 src/*.py 模块应有对应测试 —— 文件名或测试内容引用模块。

    批判者 v1.0.1 修正（自记录）: 原实现仅按测试文件名匹配，误报
    src/norm.py / src/lethality.py（其测试在 test_json_path_policy.py
    中 import 该模块）。改为文件内容级匹配。
    """
    src = repo_root / "src"
    if not src.exists():
        return
    test_files = list(tests.glob("test_*.py"))
    all_text = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore") for p in test_files)
    for mod in sorted(src.glob("*.py")):
        if mod.name == "__init__.py":
            continue
        stem = mod.stem
        if stem not in all_text and stem not in " ".join(p.stem for p in test_files):
            findings.append(_finding(
                "LOW", "T4: 模块缺测试",
                f"src/{mod.name} 未被任何 tests/test_*.py 引用",
                "新增模块应配套测试"))


def aggregate_severity(findings: list[dict]) -> str:
    if not findings:
        return "PASS"
    return max(f["severity"] for f in findings)
