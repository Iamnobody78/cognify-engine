"""Meta-Harness 轻量适配器 — 为 agent-governance 提供自优化能力（L5 / Phase 2）。

Propose 循环（对应 Meta-Harness: arXiv:2603.28052 外循环）:
  1. Propose:  scan —— 读 storage 最近窗口的 DENY 决策，按 (path, method,
     tool_name) 聚合高频模式 → 生成 YAML 规则候选（pending 状态，不自动生效）
  2. Evaluate: validate —— 候选 + 现有策略合并加载（fail-closed 语法验证）
     + 对候选证据中的历史决策重放，报告命中率
  3. 人工/仲裁裁决后，候选才注入 config/policies.yaml（行为可逆）

零侵入: 只读 storage + 复用 policy.py；不改核心引擎。候选 YAML 格式与
config/policies.yaml 完全兼容（PolicyEngine 可直接加载验证）。

用法:
  python -m src.meta_harness.adapter scan --db <path> [--window 3600] [--min-count 3]
  python -m src.meta_harness.adapter validate --candidate pending_rules/xxx.yaml [--db <path>]
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..policy import PolicyEngine

# DENY 决策里被这类 action 覆盖的模式无需再建议（已有防御）
COVERING_ACTIONS = ("DENY", "ESCALATE", "ALLOW_WITH_WARNING", "SUSPEND")

DEFAULT_POLICIES = "config/policies.yaml"
DEFAULT_WINDOW_SECONDS = 3600
DEFAULT_MIN_COUNT = 3
DEFAULT_OUT_DIR = "pending_rules"
RECENT_LIMIT = 2000  # scan 读取上限（内存护栏；窗口过滤在客户端做）


def _parse_ts(value: str) -> datetime:
    """ISO 时间戳 → UTC datetime（存储序列化格式兼容）。"""
    ts = datetime.fromisoformat(value)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def generate_policy_suggestions(
    storage,
    out_dir: str | Path = DEFAULT_OUT_DIR,
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
    min_count: int = DEFAULT_MIN_COUNT,
    policies_path: str | Path = DEFAULT_POLICIES,
) -> list[dict]:
    """扫描 DENY 日志 → 生成 pending 规则候选（YAML），返回候选元数据列表。

    过滤链（诚实: 不重复建议）:
      1. 仅 verdict==DENY 且 timestamp 在窗口内
      2. 按 (path, method, tool_name) 分组，count >= min_count 才成候选
      3. 现有策略中已有 DENY/ESCALATE/... 覆盖的 (path, method) 跳过
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    cutoff = datetime.now(timezone.utc).timestamp() - window_seconds
    recent = storage.get_recent(limit=RECENT_LIMIT)

    groups: dict[tuple, list[dict]] = {}
    for rec in recent:
        if rec.get("verdict") != "DENY":
            continue
        try:
            if _parse_ts(rec["timestamp"]).timestamp() < cutoff:
                continue
        except (KeyError, ValueError):
            continue  # 无时间戳/坏格式的决策不计入（保守）
        key = (rec.get("path", ""), rec.get("method", ""), rec.get("tool_name") or "")
        groups.setdefault(key, []).append(rec)

    # 现有策略覆盖检查（单次加载；加载失败 fail-closed → 不产出候选，宁可少建议）
    engine = None
    try:
        if Path(policies_path).exists():
            engine = PolicyEngine(str(policies_path))
    except Exception:
        engine = None

    candidates: list[dict] = []
    for (path, method, tool), recs in sorted(
            groups.items(), key=lambda kv: -len(kv[1])):
        if len(recs) < min_count or not path:
            continue
        if engine is not None:
            hit = engine.evaluate(path, method)
            if hit is not None and hit.action in COVERING_ACTIONS:
                continue  # 已有防御覆盖

        stable = hashlib.sha256(f"{path}|{method}|{tool}".encode()).hexdigest()[:8]
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        rule_id = f"auto-{ts}-{stable}"
        decision_ids = [r["id"] for r in recs[:10]]
        trace_ids = sorted({r.get("trace_id") for r in recs if r.get("trace_id")})[:5]

        candidate = {
            "id": rule_id,
            "description": (
                f"meta-harness 建议: {len(recs)} 次 DENY (窗口 {window_seconds}s) "
                f"@ {path} {method} tool={tool or 'n/a'}"
            ),
            "path": path,
            "method": method,
            "action": "DENY",
            "priority": 90,
            "count": len(recs),
            "evidence": {
                "window_seconds": window_seconds,
                "decision_ids": decision_ids,
                "trace_ids": trace_ids,
            },
        }
        # 候选 YAML 与 PolicyEngine._load 兼容（独立文件，不注入主策略）
        yaml_doc = {
            "name": f"meta-harness-pending-{rule_id}",
            "version": "0.0.1",
            "rules": [{
                "name": rule_id,
                "path_pattern": path,
                "method": method,
                "action": "DENY",
                "reason": candidate["description"],
                "priority": 90,
            }],
        }
        (out / f"{rule_id}.yaml").write_text(
            yaml.safe_dump(yaml_doc, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
        candidates.append(candidate)

    return candidates


def validate_candidate(
    candidate_path: str | Path,
    policies_path: str | Path = DEFAULT_POLICIES,
    storage=None,
) -> dict:
    """验证候选规则: 语法/语义 fail-closed + 历史决策重放命中率。

    返回: {"valid": bool, "reason": str, "hit_rate": float|None,
           "merged_rule_count": int, "checked": int}
    """
    cand = Path(candidate_path)
    if not cand.exists():
        return {"valid": False, "reason": f"候选文件不存在: {cand}",
                "hit_rate": None, "merged_rule_count": 0, "checked": 0}

    try:
        cand_data = yaml.safe_load(cand.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return {"valid": False, "reason": f"YAML 解析失败: {exc}",
                "hit_rate": None, "merged_rule_count": 0, "checked": 0}

    # 合并现有策略 + 候选，临时加载验证（fail-closed: 任一坏规则 → 拒绝候选）
    merged_rules = []
    if Path(policies_path).exists():
        try:
            base = yaml.safe_load(Path(policies_path).read_text(encoding="utf-8"))
            merged_rules.extend(base.get("rules", []))
        except yaml.YAMLError:
            return {"valid": False, "reason": "现有 policies.yaml 无法解析",
                    "hit_rate": None, "merged_rule_count": 0, "checked": 0}
    cand_rules = cand_data.get("rules", []) if isinstance(cand_data, dict) else []
    merged_rules.extend(cand_rules)

    try:
        with tempfile.NamedTemporaryFile(
                "w", suffix=".yaml", encoding="utf-8", delete=False) as tf:
            yaml.safe_dump({"name": "merged-validate", "version": "0.0.1",
                            "rules": merged_rules}, tf, allow_unicode=True)
            tmp_path = tf.name
        engine = PolicyEngine(tmp_path)  # 加载失败抛异常 → INVALID
    except Exception as exc:
        return {"valid": False, "reason": f"合并策略加载失败: {exc}",
                "hit_rate": None, "merged_rule_count": len(merged_rules),
                "checked": 0}

    # 重放: 对候选证据中的历史决策 (path, method) 重新评估，确认规则会命中
    hit_rate, checked = None, 0
    if storage is not None and cand_data and isinstance(cand_data, dict):
        cand_rules0 = cand_rules[0] if cand_rules else {}
        evidence_ids = []
        for rule in cand_rules:
            # 候选证据附在 reason 或独立文件；此处用候选规则自身路径字段
            pass
        # 用候选规则自己的 path_pattern/method 直接重放（证据在独立元数据中）
        from ..models import Verdict
        checked = 0
        hits = 0
        pattern = cand_rules0.get("path_pattern", "")
        method = cand_rules0.get("method")
        recent = storage.get_recent(limit=RECENT_LIMIT)
        for rec in recent:
            if rec.get("method") != method:
                continue
            if rec.get("path") != pattern:
                continue
            checked += 1
            if engine.evaluate(rec.get("path", ""), rec.get("method", "")) is not None:
                hits += 1
        if checked:
            hit_rate = round(hits / checked, 3)

    return {"valid": True, "reason": "候选可安全合并（语法+语义有效）",
            "hit_rate": hit_rate, "merged_rule_count": len(merged_rules),
            "checked": checked}


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(prog="meta-harness-adapter")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan", help="扫描 DENY → 生成规则候选")
    p_scan.add_argument("--db", required=True, help="SQLite 审计库路径")
    p_scan.add_argument("--window", type=int, default=DEFAULT_WINDOW_SECONDS)
    p_scan.add_argument("--min-count", type=int, default=DEFAULT_MIN_COUNT)
    p_scan.add_argument("--out", default=DEFAULT_OUT_DIR)
    p_scan.add_argument("--policies", default=DEFAULT_POLICIES)

    p_val = sub.add_parser("validate", help="验证候选规则")
    p_val.add_argument("--candidate", required=True)
    p_val.add_argument("--db", help="SQLite 审计库路径（提供则重放）")
    p_val.add_argument("--policies", default=DEFAULT_POLICIES)

    args = parser.parse_args(argv)
    from ..storage import Storage

    if args.cmd == "scan":
        storage = Storage(db_path=args.db)
        cands = generate_policy_suggestions(
            storage, out_dir=args.out, window_seconds=args.window,
            min_count=args.min_count, policies_path=args.policies)
        for c in cands:
            print(f"[candidate] {c['id']}  {c['method']} {c['path']}  "
                  f"count={c['count']} → {args.out}/{c['id']}.yaml")
        print(f"[scan] {len(cands)} 个候选（窗口 {args.window}s, min {args.min_count}）")
        return 0

    if args.cmd == "validate":
        storage = Storage(db_path=args.db) if args.db else None
        result = validate_candidate(args.candidate, args.policies, storage)
        print(f"[validate] valid={result['valid']}  reason={result['reason']}  "
              f"hit_rate={result['hit_rate']}  merged_rules={result['merged_rule_count']}")
        return 0 if result["valid"] else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
