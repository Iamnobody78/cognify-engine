"""deployer — P12 部署层: 执行确定性修复 + 验证 + 提交/回滚。

动作表（ACTIONS）:
  - REGENERATE_CODEGEN: 重新生成 src/codegen/_generated_matches.py
    （确定性，逐字节可复现; 幂等 → 无漂移时不变更文件）

流程（每次动作）:
  generate → verify (pytest 回归) → commit (+push 可选) 
  verify 失败 → rollback (git checkout 还原) → 记录诊断

人类 in-the-loop 契约:
  - commit 自动执行（确定性产物）
  - push 仅当 auto_push=True（默认 False）— 最终推送需人工确认
  - 非确定性修复（策略合并 deploy_candidate）不在本层执行,
    由调度器显式上报需人工
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from src.codegen.generator import generate

from .sensor import CODEGEN_OUT_REL, CODEGEN_POLICY_REL

# 动作键 → 描述（与 diagnoser.ACTION_* 对应）
ACTIONS = {
    "REGENERATE_CODEGEN": "重新生成 codegen 产物",
}

# 可自动提交的路径白名单（仅确定性产物，绝不触碰他人改动）
_AUTO_COMMIT_PATHS = ("src/codegen/_generated_matches.py",)


class RollbackRequired(Exception):
    """验证失败，需要回滚。"""


def _git(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(repo_root), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60,
    )


def generate_fix(action: str, repo_root: str | Path) -> dict:
    """按动作生成候选修复。返回 {"changed": [Path], "detail": str}。"""
    root = Path(repo_root)
    if action == "REGENERATE_CODEGEN":
        policy = root / CODEGEN_POLICY_REL
        out = root / CODEGEN_OUT_REL
        written, diags = generate(policy, out)
        return {
            "changed": [out] if written else [],
            "detail": "; ".join(diags) if diags else ("已重新生成" if written else "无漂移（幂等）"),
            "action": action,
        }
    raise ValueError(f"未知动作: {action}")


def verify_fix(repo_root: str | Path, changed: list[Path],
               tests_dir: str = "tests", run_tests: bool = True) -> dict:
    """验证修复: 语法编译 + 可选 pytest 回归。

    返回 {"verified": bool, "detail": str, "tests": dict|None}
    """
    from src.meta_harness.sandbox import run_pytest_regression

    # 1. 语法编译检查（fail-closed）
    for path in changed:
        if path.suffix == ".py":
            proc = subprocess.run(
                ["python", "-m", "py_compile", str(path)],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=60)
            if proc.returncode != 0:
                return {"verified": False,
                        "detail": f"语法错误 @ {path}: {proc.stderr.strip()}",
                        "tests": None}

    # 2. 回归
    tests = None
    if run_tests:
        tests = run_pytest_regression(tests_dir)
        if not tests["tests_passed"]:
            return {"verified": False,
                    "detail": f"pytest 回归失败: {tests['summary']}",
                    "tests": tests}

    detail = "语法通过" + (f"; pytest: {tests['summary']}" if tests else "")
    return {"verified": True, "detail": detail, "tests": tests}


def commit_fix(repo_root: str | Path, changed: list[Path], action: str,
               detail: str) -> dict:
    """提交确定性修复（仅白名单路径）。返回 {"committed": bool, "hash": str}。"""
    root = Path(repo_root)
    safe = []
    for p in changed:
        rel = Path(p).resolve().relative_to(root.resolve()).as_posix()
        if rel in _AUTO_COMMIT_PATHS:
            safe.append(rel)
    if not safe:
        return {"committed": False, "hash": "", "detail": "无可提交路径（白名单外）"}

    for rel in safe:
        _git(root, ["add", "--", rel])
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    msg = f"[bootstrap] {action} ({ts}) — {detail[:120]}"
    proc = _git(root, ["commit", "-m", msg])
    if proc.returncode != 0:
        return {"committed": False, "hash": "", "detail": (proc.stderr or proc.stdout).strip()}
    # 提取 hash
    rev = _git(root, ["rev-parse", "--short", "HEAD"])
    return {"committed": True, "hash": rev.stdout.strip() if rev.returncode == 0 else "",
            "detail": msg}


def push_fix(repo_root: str | Path) -> dict:
    """推送（需显式 auto_push=True 且环境变量门禁打开）。

    P0-1: 门禁 (CONTEXT_HMAC_KEY + GATE_8_SKIP 同时存在) 未开时不推送,
    返回 pushed=False + 原因 —— 提交已完成, 推送降级为人工确认。
    """
    from .scheduler import _push_gate_open
    if not _push_gate_open():
        return {"pushed": False,
                "detail": "门禁未开: 需 CONTEXT_HMAC_KEY 与 GATE_8_SKIP 同时存在"
                          "(CI 专用); 提交已完成, 推送待人工确认"}
    root = Path(repo_root)
    proc = _git(root, ["push"])
    if proc.returncode != 0:
        return {"pushed": False, "detail": (proc.stderr or proc.stdout).strip()}
    return {"pushed": True, "detail": "push 成功"}


def rollback(repo_root: str | Path, changed: list[Path]) -> dict:
    """回滚: git checkout 还原生成物。返回 {"rolled_back": bool, "detail": str}。"""
    root = Path(repo_root)
    if not changed:
        return {"rolled_back": False, "detail": "无变更需回滚"}
    rels = [Path(p).resolve().relative_to(root.resolve()).as_posix() for p in changed]
    for rel in rels:
        _git(root, ["checkout", "--", rel])
    return {"rolled_back": True, "detail": f"已还原: {', '.join(rels)}"}


def run_fix(action: str, repo_root: str | Path, *,
            auto_push: bool = False, run_tests: bool = True,
            tests_dir: str = "tests") -> dict:
    """执行单个动作的完整闭环（生成→验证→提交/回滚）。

    返回统一结果字典（含 diagnosis 记录与 repair_chain 因果链）:
      {"action", "status": "DEPLOYED|ROLLED_BACK|NOOP|FAILED",
       "detail", "commit", "tests", "repair_chain"}
    """
    chain = {"problem": action, "diagnosis": "codegen 漂移检测",
             "fix": "", "verification": ""}
    try:
        result = generate_fix(action, repo_root)
    except Exception as exc:  # noqa: BLE001 — 确定性失败也须入诊断
        chain.update(fix=f"生成失败: {exc}", verification="未验证")
        return {"action": action, "status": "FAILED",
                "detail": f"生成失败: {exc}", "commit": None, "tests": None,
                "repair_chain": chain}
    chain["fix"] = result["detail"]

    if not result["changed"]:
        chain.update(verification="幂等: 无变更")
        return {"action": action, "status": "NOOP",
                "detail": result["detail"], "commit": None, "tests": None,
                "repair_chain": chain}

    verify = verify_fix(repo_root, result["changed"],
                        tests_dir=tests_dir, run_tests=run_tests)
    chain["verification"] = verify["detail"]
    if not verify["verified"]:
        rb = rollback(repo_root, result["changed"])
        chain.update(verification=f"{verify['detail']} → 已回滚")
        return {
            "action": action, "status": "ROLLED_BACK",
            "detail": f"验证失败→回滚: {verify['detail']} | {rb['detail']}",
            "commit": None, "tests": verify["tests"], "repair_chain": chain,
        }

    commit = commit_fix(repo_root, result["changed"], action, verify["detail"])
    pushed = None
    if commit["committed"] and auto_push:
        pushed = push_fix(repo_root)
    return {
        "action": action,
        "status": "DEPLOYED" if commit["committed"] else "NOOP",
        "detail": (f"{result['detail']} | {verify['detail']} | "
                   f"{commit['detail']}"
                   + (f" | {pushed['detail']}" if pushed else " | push 跳过(需人工确认)")),
        "commit": commit,
        "tests": verify["tests"],
        "repair_chain": chain,
    }
