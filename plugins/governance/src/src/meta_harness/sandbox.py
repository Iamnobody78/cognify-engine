"""Meta-Harness 完整评估沙箱（L5 / Phase 3）。

在 Phase 2 适配器（validate_candidate）之上增加三层:
  1. 冲突检测: 候选规则与现有规则 (path_pattern, method) 重叠且 action 冲突
     → fail-closed 不可部署（需人工/仲裁裁决）
  2. 回归验证: subprocess 运行 pytest → 代码基线无回归（tests_passed）
  3. 可逆部署: backup 现有 policies.yaml → 合并候选（按 name 去重）→ 写回;
     显式操作（人工裁决后调用），行为可逆（backup + git 历史）

诚实边界（写入沙箱语义）:
  - pytest 验证的是【代码基线无回归】——候选策略本身不参与现有测试的
    运行时加载（测试自带 fixture 策略）
  - hit_rate 是历史 DENY 重放（候选应命中的【下限证据】）——真实流量下的
    效果需部署后观察，沙箱无法模拟真实 LLM 请求分布
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..policy import PolicyEngine
from .adapter import DEFAULT_POLICIES, validate_candidate

SANDBOX_VERSION = "0.1.0"


def _load_policies(policies_path: Path) -> list[dict]:
    if not policies_path.exists():
        return []
    data = yaml.safe_load(policies_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return []
    return list(data.get("rules", []))


def _load_candidate(candidate_path: Path) -> tuple[dict | None, str]:
    """读取候选 YAML，返回 (candidate_dict, 错误信息)。"""
    if not candidate_path.exists():
        return None, f"候选文件不存在: {candidate_path}"
    try:
        data = yaml.safe_load(candidate_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return None, f"候选 YAML 解析失败: {exc}"
    if not isinstance(data, dict) or not data.get("rules"):
        return None, "候选文件无 rules 段"
    return data, ""


def check_conflicts(candidate_path: Path, policies_path: Path) -> list[dict]:
    """候选 vs 现有规则冲突检测（同 path+method 且 action 不同 → 冲突）。"""
    cand, err = _load_candidate(candidate_path)
    if err:
        return [{"severity": "ERROR", "detail": err}]
    cand_rules = cand["rules"]
    base_rules = _load_policies(Path(policies_path))
    conflicts: list[dict] = []
    for c in cand_rules:
        for b in base_rules:
            same_key = (b.get("path_pattern") == c.get("path_pattern")
                        and b.get("method") == c.get("method"))
            if not same_key:
                continue
            if b.get("action") != c.get("action"):
                conflicts.append({
                    "severity": "HIGH",
                    "detail": (f"候选 {c.get('name')} action={c.get('action')} "
                               f"与现有 {b.get('name')} action={b.get('action')} "
                               f"冲突 @ {c.get('path_pattern')} {c.get('method')}"),
                })
            else:
                conflicts.append({
                    "severity": "LOW",
                    "detail": (f"候选 {c.get('name')} 与现有 {b.get('name')} 冗余 "
                               f"（同 action 同 path+method）"),
                })
    return conflicts


def run_pytest_regression(tests_dir: str | Path = "tests",
                          timeout: int = 600) -> dict:
    """subprocess 运行 pytest 全量回归。返回真实输出摘要（防伪造原则）。"""
    cmd = [sys.executable, "-m", "pytest", str(tests_dir), "-q", "--no-header"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return {"tests_passed": False, "exit_code": -1,
                "summary": f"pytest 超时（>{timeout}s）"}
    tail = (proc.stdout or "").strip().splitlines()
    summary = tail[-1] if tail else "(无输出)"
    return {
        "tests_passed": proc.returncode == 0,
        "exit_code": proc.returncode,
        "summary": summary,
    }


def evaluate_candidate_in_sandbox(
    candidate_path: str | Path,
    policies_path: str | Path = DEFAULT_POLICIES,
    storage=None,
    run_tests: bool = False,
    tests_dir: str | Path = "tests",
) -> dict:
    """完整沙箱评估: 语法 + 冲突 + 重放 + 可选 pytest 回归。

    返回: {"deployable": bool, "reasons": [str], "conflicts": [dict],
           "hit_rate": float|None, "tests": dict|None, "checked": int}
    """
    cand = Path(candidate_path)
    reasons: list[str] = []

    # 1. 语法/语义验证（复用 Phase 2 validate_candidate，fail-closed）
    base = validate_candidate(cand, policies_path, storage=storage)
    if not base["valid"]:
        return {"deployable": False, "reasons": [base["reason"]],
                "conflicts": [], "hit_rate": None, "tests": None,
                "checked": 0}

    # 2. 冲突检测（新增）
    conflicts = check_conflicts(cand, Path(policies_path))
    high_conflicts = [c for c in conflicts if c["severity"] == "HIGH"]
    if high_conflicts:
        reasons.append(f"存在 {len(high_conflicts)} 个 action 冲突（需人工裁决）")
    else:
        reasons.append("无 action 冲突")

    # 3. 重放命中率（validate_candidate 已算，取回）
    hit_rate = base.get("hit_rate")

    # 4. 可选回归验证
    tests = None
    if run_tests:
        tests = run_pytest_regression(tests_dir)
        if not tests["tests_passed"]:
            reasons.append(f"pytest 回归失败: {tests['summary']}")
        else:
            reasons.append(f"pytest 回归通过: {tests['summary']}")

    deployable = base["valid"] and not high_conflicts and (tests is None or tests["tests_passed"])
    return {
        "deployable": deployable,
        "reasons": reasons,
        "conflicts": conflicts,
        "hit_rate": hit_rate,
        "tests": tests,
        "checked": base.get("checked", 0),
    }


def deploy_candidate(
    candidate_path: str | Path,
    policies_path: str | Path = DEFAULT_POLICIES,
    backup: bool = True,
) -> dict:
    """显式部署: 备份 → 合并（按 name 去重）→ 写回 policies.yaml。

    行为可逆: backup=True 时创建 policies.yaml.bak-<ts>；git 历史可回滚。
    仅当人工/仲裁裁决采纳后调用（沙箱 evaluate deployable=True 为前提）。
    """
    cand = Path(candidate_path)
    pol = Path(policies_path)
    cand_data, err = _load_candidate(cand)
    if err:
        return {"deployed": False, "error": err}

    existing = _load_policies(pol)
    existing_names = {r.get("name") for r in existing if r.get("name")}
    added = 0
    for rule in cand_data["rules"]:
        name = rule.get("name")
        if name and name in existing_names:
            existing = [r for r in existing if r.get("name") != name]  # 替换
        existing.append(rule)
        added += 1

    backup_path = None
    if backup and pol.exists():
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = pol.with_name(f"{pol.name}.bak-{ts}")
        backup_path.write_text(pol.read_text(encoding="utf-8"), encoding="utf-8")

    pol.parent.mkdir(parents=True, exist_ok=True)
    pol.write_text(yaml.safe_dump(
        {"name": _existing_name(pol) or "governance",
         "version": _existing_version(pol) or "0.0.1",
         "rules": existing},
        allow_unicode=True, sort_keys=False), encoding="utf-8")

    return {"deployed": True, "added": added,
            "total_rules": len(existing), "backup_path": str(backup_path)}


def _existing_name(pol: Path) -> str | None:
    if not pol.exists():
        return None
    data = yaml.safe_load(pol.read_text(encoding="utf-8"))
    return data.get("name") if isinstance(data, dict) else None


def _existing_version(pol: Path) -> str | None:
    if not pol.exists():
        return None
    data = yaml.safe_load(pol.read_text(encoding="utf-8"))
    return data.get("version") if isinstance(data, dict) else None


def generate_eval_report(candidate_path: str | Path, result: dict) -> str:
    """生成评估报告 markdown（含证据链，供人工裁决）。"""
    cand = Path(candidate_path)
    lines = [
        "## 🧪 Meta-Harness 沙箱评估报告",
        "",
        f"- 候选: `{cand.name}`",
        f"- 时间: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"- 裁决: {'✅ 可部署' if result['deployable'] else '⛔ 不可部署'}",
        f"- 命中率(历史 DENY 重放): {result['hit_rate']}",
        f"- 检查决策数: {result['checked']}",
        "",
        "### 理由",
    ]
    lines += [f"- {r}" for r in result["reasons"]] or ["- （无）"]
    lines += ["", "### 冲突", ""]
    lines += [f"- [{c['severity']}] {c['detail']}" for c in result["conflicts"]] or ["- 无"]
    if result.get("tests"):
        lines += ["", "### 回归", "",
                  f"- pytest: {'PASS' if result['tests']['tests_passed'] else 'FAIL'} "
                  f"| exit={result['tests']['exit_code']} | {result['tests']['summary']}"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(prog="meta-harness-sandbox")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ev = sub.add_parser("evaluate", help="沙箱评估候选")
    p_ev.add_argument("--candidate", required=True)
    p_ev.add_argument("--policies", default=DEFAULT_POLICIES)
    p_ev.add_argument("--db", help="审计库（提供则重放）")
    p_ev.add_argument("--run-tests", action="store_true", help="运行 pytest 回归")
    p_ev.add_argument("--report", help="评估报告输出路径")

    p_dep = sub.add_parser("deploy", help="部署候选（需人工裁决后显式调用）")
    p_dep.add_argument("--candidate", required=True)
    p_dep.add_argument("--policies", default=DEFAULT_POLICIES)
    p_dep.add_argument("--no-backup", action="store_true")

    args = parser.parse_args(argv)
    from ..storage import Storage

    if args.cmd == "evaluate":
        storage = Storage(db_path=args.db) if args.db else None
        result = evaluate_candidate_in_sandbox(
            args.candidate, args.policies, storage=storage, run_tests=args.run_tests)
        print(f"[sandbox] deployable={result['deployable']}")
        for r in result["reasons"]:
            print(f"  - {r}")
        print(f"[sandbox] hit_rate={result['hit_rate']} checked={result['checked']}")
        if args.report:
            Path(args.report).write_text(
                generate_eval_report(args.candidate, result), encoding="utf-8")
            print(f"[sandbox] 评估报告: {args.report}")
        return 0 if result["deployable"] else 1

    if args.cmd == "deploy":
        result = deploy_candidate(args.candidate, args.policies,
                                  backup=not args.no_backup)
        print(f"[deploy] {result}")
        return 0 if result.get("deployed") else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
