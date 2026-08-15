# -*- coding: utf-8 -*-
"""
Anti-Drift 看门狗 v1.0 — 元系统修改的审计与校验闸门（带锚点的递归）

三闸门:
  闸门1: 原则对齐检查 (5 条金刚石锚点)
  闸门2: 影响评估 (目标层级 L0-L3, 破坏性变更拒绝)
  闸门3: 沙箱验证 (备份 + 试运行 + 回滚)

用法:
  python anti_drift_watchdog.py --check <target_file>          # 检查目标是否触及锚点
  python anti_drift_watchdog.py --propose <proposal.json>      # 三闸门评估修改提案
  python anti_drift_watchdog.py --history                      # 查看修改历史
  python anti_drift_watchdog.py --self-audit                   # 元元监控报告
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TRACE_DIR = os.path.dirname(os.path.abspath(__file__))
META_EVOL_DIR = os.path.join(REPO_ROOT, "governance", "meta_evolution")
HISTORY_LOG = os.path.join(META_EVOL_DIR, "meta_interventions.log")
DRIFT_DIR = os.path.join(META_EVOL_DIR, "meta_drift_reports")
ANCHORS_FILE = os.path.join(TRACE_DIR, "diamond_anchors.md")

# 5 条金刚石锚点: 原则 -> 违规模式 (语义关键词/正则)
ANCHORS = {
    "P1_sovereign_not_transferable": [
        r"\bhuman\b.*\bremove|remove.*\bhuman\b", r"\boverride\s+(human|user)\b",
        r"\bbypass\s+(human|user|approval)\b", r"\bself\s*approve\b",
        r"人类.*(废除|移除|绕过)", r"(废除|移除|绕过).*人类",
    ],
    "P2_cognition_traceable": [
        r"\bdelete\s+(trace|log|history|decision_log)\b", r"\bpurge\s+(evidence|trace)\b",
        r"删除.*(证据|日志|追溯)", r"(关闭|禁用).*(追溯|证据)",
    ],
    "P3_decision_revertable": [
        r"\bdisable\s+rollback\b", r"\bno\s+rollback\b", r"禁止.*回滚", r"删除.*回滚",
    ],
    "P4_boundary_honest": [
        r"\bhide\s+boundary\b", r"\bsuppress\s+boundary\b", r"隐藏.*边界", r"不再.*声明.*边界",
    ],
    "P5_recursion_bounded": [
        r"\bunlimited\s+recursion\b", r"\binfinite\s+(loop|recursion)\b", r"无限递归",
        r"递归.*(无上限|无限)", r"深度.*(>3|大于3|4|5|10)",
    ],
}

# 修改权限层级 (对齐 diamond_anchors.md 递归边界)
LEVELS = {
    "L0": {"match": r"diamond_anchors\.md|governance[\\/]core[\\/]|\.aionui[\\/]anchors", "perm": "HARD_BLOCK", "gates": 3},
    "L1": {"match": r"meta_prompts[\\/](mef_os|mmce_sys|anti_drift)", "perm": "PROPOSE_ONLY", "gates": 3},
    "L2": {"match": r"engineering_rules\.md|meta_engineering_rules\.md|meta_config", "perm": "AUTO_2GATES", "gates": 2},
    "L3": {"match": r"knowledge_base|trace[\\/]|meta_evolution", "perm": "AUTO_TRACE", "gates": 1},
}

IMPACT_SEVERITY = {"L0": 5, "L1": 3, "L2": 2, "L3": 1}


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_dirs():
    os.makedirs(META_EVOL_DIR, exist_ok=True)
    os.makedirs(DRIFT_DIR, exist_ok=True)


def classify_target(path):
    """按路径判定递归层级 (L0-L3)。"""
    p = path.replace("\\", "/")
    for level, spec in LEVELS.items():
        if re.search(spec["match"], p, re.IGNORECASE):
            return level
    return "L3"  # 默认最低权限层级


def detect_violations(text):
    """闸门1: 扫描文本是否触及金刚石锚点。"""
    violations = []
    for principle, patterns in ANCHORS.items():
        for pat in patterns:
            if re.search(pat, text, re.IGNORECASE):
                violations.append({"principle": principle, "pattern": pat})
                break
    return violations


def gate1_principle(text):
    violations = detect_violations(text)
    if violations:
        return {"passed": False, "violations": violations}
    return {"passed": True, "violations": []}


def gate2_impact(target_path, changes_summary=""):
    """闸门2: 影响评估 — 按目标层级 + 变更面判定严重度。"""
    level = classify_target(target_path)
    severity = IMPACT_SEVERITY.get(level, 1)
    # 变更面惩罚: 删除/重写操作加重
    extra = 0
    if re.search(r"\b(delete|remove|overwrite|rm)\b", changes_summary, re.IGNORECASE):
        extra = 1
    if severity + extra > 2:
        return {"passed": False, "severity": severity + extra, "level": level,
                "reason": "破坏性变更 (severity>2)"}
    return {"passed": True, "severity": severity + extra, "level": level}


def gate3_sandbox(target_path):
    """闸门3: 沙箱验证 — 备份目标文件, 确认可回滚。"""
    if not os.path.exists(target_path):
        return {"passed": True, "reason": "目标不存在(新建操作), 沙箱视为安全", "backup": None}
    try:
        tmp = tempfile.mkdtemp(prefix="wd_sandbox_")
        backup = os.path.join(tmp, os.path.basename(target_path) + ".bak")
        shutil.copy2(target_path, backup)
        ok = os.path.exists(backup) and os.path.getsize(backup) == os.path.getsize(target_path)
        return {"passed": ok, "reason": "备份成功, 可回滚" if ok else "备份失败",
                "backup": backup if ok else None}
    except Exception as e:
        return {"passed": False, "reason": "沙箱异常: %s" % e, "backup": None}


def log_intervention(entry):
    ensure_dirs()
    with open(HISTORY_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def evaluate_proposal(proposal):
    """三闸门完整评估。proposal: {target, summary, author}"""
    target = proposal.get("target", "")
    summary = proposal.get("summary", proposal.get("reason", ""))
    text = summary + " " + target

    g1 = gate1_principle(text)
    g2 = gate2_impact(target, summary)
    level = classify_target(target)
    gates_needed = LEVELS[level]["gates"]

    result = {
        "ts": now_iso(),
        "target": target,
        "level": level,
        "gates_required": gates_needed,
        "gate1_principle": g1,
        "gate2_impact": g2,
    }
    if not g1["passed"]:
        result["status"] = "REJECTED_GATE1"
    elif level == "L0":
        result["status"] = "HARD_BLOCKED_ANCHOR"
    elif not g2["passed"]:
        result["status"] = "REJECTED_GATE2"
    elif gates_needed >= 3:
        g3 = gate3_sandbox(target)
        result["gate3_sandbox"] = g3
        if not g3["passed"]:
            result["status"] = "REJECTED_GATE3"
        else:
            result["status"] = "APPROVED_NEEDS_HUMAN"  # L1 需人类确认 (L0 阶段权限)
    else:
        result["status"] = "APPROVED" if gates_needed == 1 else "APPROVED_NEEDS_HUMAN"
    result["verdict"] = result["status"]
    log_intervention({"type": "watchdog_eval", **result})
    return result


def self_audit():
    """元元监控: 拒绝率 / 修改频率 / 人类介入率。"""
    ensure_dirs()
    entries = []
    if os.path.exists(HISTORY_LOG):
        with open(HISTORY_LOG, encoding="utf-8") as f:
            for line in f:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    evals = [e for e in entries if e.get("type") == "watchdog_eval"]
    rejected = [e for e in evals if e.get("status", "").startswith(("REJECTED", "HARD_BLOCK"))]
    n = len(evals)
    report = {
        "ts": now_iso(),
        "total_evaluations": n,
        "rejection_rate": round(len(rejected) / n, 3) if n else None,
        "modifications_this_week": len([e for e in evals if e.get("status") in ("APPROVED", "APPROVED_NEEDS_HUMAN")]),
        "flag": None,
    }
    if n and len(rejected) / n > 0.3:
        report["flag"] = "watchdog_too_strict"
    if report["modifications_this_week"] > 5:
        report["flag"] = "meta_system_unstable"
    drift_file = os.path.join(DRIFT_DIR, "drift_%s.json" % now_iso().replace(":", "").replace("-", ""))
    with open(drift_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report, drift_file


def main():
    ap = argparse.ArgumentParser(description="Anti-Drift 看门狗 v1.0")
    ap.add_argument("--check", metavar="FILE", help="检查目标文件是否触及锚点")
    ap.add_argument("--propose", metavar="PROPOSAL_JSON", help="评估修改提案 (JSON 文件)")
    ap.add_argument("--history", action="store_true", help="查看修改历史")
    ap.add_argument("--self-audit", action="store_true", help="元元监控报告")
    args = ap.parse_args()

    if args.check:
        p = os.path.abspath(args.check)
        if not os.path.exists(p):
            print(json.dumps({"error": "file not found", "path": p}, ensure_ascii=False))
            return 1
        with open(p, encoding="utf-8", errors="replace") as f:
            text = f.read()
        level = classify_target(p)
        violations = detect_violations(text)
        result = {"target": p, "level": level, "violations": violations,
                  "status": "HARD_BLOCK" if (violations or level == "L0" and _is_anchor_file(p)) else "OK"}
        if level == "L0":
            result["status"] = "HARD_BLOCK_ANCHOR_FILE" if _is_anchor_file(p) else result["status"]
        log_intervention({"type": "watchdog_check", "ts": now_iso(), **result})
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "OK" else 2

    if args.propose:
        with open(args.propose, encoding="utf-8") as f:
            proposal = json.load(f)
        result = evaluate_proposal(proposal)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"].startswith("APPROVED") else 2

    if args.history:
        if os.path.exists(HISTORY_LOG):
            with open(HISTORY_LOG, encoding="utf-8") as f:
                print(f.read())
        else:
            print("(no history)")
        return 0

    if args.self_audit:
        report, drift_file = self_audit()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print("drift_report:", drift_file)
        return 0

    ap.print_help()
    return 1


def _is_anchor_file(path):
    return os.path.basename(path) in ("diamond_anchors.md", "anti_drift_watchdog.py")


if __name__ == "__main__":
    sys.exit(main())
