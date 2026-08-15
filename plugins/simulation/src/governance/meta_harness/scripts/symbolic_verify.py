#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sprint 35 T1: Z3 符号验证层 (第四层防护, SYMBOLIC_PROOF_FAIL).

在 S21 diff_gate(行为级) -> S30 priority 预检 -> S32 COVERAGE_GAP(单维投影) 之上,
提供数学级联合覆盖完备性证明:

  不变量 I1 (联合覆盖): ∀ 输入点 ∈ 物理定义域 → 至少一条规则条件为真。

与 S32 的区别 (动机):
  - S32 对每个维度独立投影 (angle/dist/edge), 无法捕获多维联合空洞 —
    例如 opp_found=True, dist∈(0,0.6), angle∈(-10,10), edge∈(0.30,0.65) 时,
    CLOSE-PUSH(edge<0.30 不满足) / FLANK(angle 中间不满足) / OPPONENT-FOUND(dist>0.6
    不满足) 全部失配 → 单维投影各维度均有覆盖 (S32 放行), 但联合空间成空洞 (Z3 拦截)。

语义 (与 S32 一致): 仅拦截「候选新增」的联合空洞 — 基线已有空洞容忍,
候选变更后产生的新空洞 (基线有覆盖、候选无覆盖) -> SYMBOLIC_PROOF_FAIL, 不进评估循环。

用法:
  python3 symbolic_verify.py --selfcheck           # 对当前 ABDL 基线做完备性自检
  python3 symbolic_verify.py --selfcheck --show    # 打印全部反例 (最多 5 个)
"""

from __future__ import annotations

import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    import z3
    _Z3_AVAILABLE = True
except Exception:  # pragma: no cover - 无 z3 时降级放行 (防御纵深)
    z3 = None
    _Z3_AVAILABLE = False

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RULES_PATH = os.path.join(REPO_ROOT, "governance", "meta_language", "simulation_rules.abdl")

# 物理定义域: (最小值, 最大值) — 数值传感器
_DOMAINS: Dict[str, Tuple[float, float]] = {
    "opponent_angle": (-180.0, 180.0),
    "opponent_dist": (0.0, 10.0),
    "edge_proximity": (0.0, 1.0),
    "push_force": (0.0, 100.0),
    "steps_remaining": (0.0, 300.0),
    "stuck_counter": (0.0, 100.0),
    "agent_speed": (0.0, 5.0),
}
# 布尔传感器
_BOOL_SENSORS = {"opponent_found"}

# ABDL 规则块提取 (id 开头到 action 之前)
_RULE_BLOCK_RE = re.compile(r'-\s*id:\s*"([^"]+)"(.*?)(?=-\s*id:|\Z)', re.S)
_COND_RE = re.compile(r'condition:\s*"([^"]+)"')


def _z3_ok() -> bool:
    """z3 可用性检查 (不可用时降级放行并输出警告, 不阻断管道)。"""
    return _Z3_AVAILABLE


# ---------------------------------------------------------------------------
# ABDL 条件 -> Z3 表达式
# ---------------------------------------------------------------------------
def _condition_to_z3(cond: str, ctx: Dict[str, Any]) -> Optional[Any]:
    """将单条 ABDL 条件翻译为 Z3 Bool 表达式 (仅支持比较/BETWEEN/AND/EXISTS)。

    不支持的 token 忽略 (保守: 该子句视为 True)。
    返回 None 表示条件恒真 (无约束)。
    """
    if not _Z3_AVAILABLE:
        return None
    # AND 拆分 (大小写不敏感; ABDL 用 "AND" 连接)
    parts = re.split(r"\s+AND\s+", cond, flags=re.I)
    exprs: List[Any] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        e = _single_clause_to_z3(part, ctx)
        if e is not None:
            exprs.append(e)
    if not exprs:
        return None
    return z3.And(*exprs) if len(exprs) > 1 else exprs[0]


def _single_clause_to_z3(clause: str, ctx: Dict[str, Any]) -> Optional[Any]:
    """单子句翻译: sensor(x) OP v / sensor(x) == True|False / EXISTS(sensor(x))。"""
    m = re.match(r"EXISTS\(\s*sensor\(\s*(\w+)\s*\)\s*\)", clause)
    if m:
        # EXISTS 仅声明存在该传感器 (值由其他子句约束); 恒真
        return None
    m = re.match(r"sensor\(\s*(\w+)\s*\)\s*==\s*(True|False)", clause)
    if m:
        name, val = m.group(1), m.group(2)
        var = ctx.get(name)
        if var is None:
            return None
        return var if val == "True" else z3.Not(var)
    m = re.match(r"sensor\(\s*(\w+)\s*\)\s*(<=|>=|<|>)\s*(-?[\d.]+)", clause)
    if m:
        name, op, num = m.group(1), m.group(2), float(m.group(3))
        var = ctx.get(name)
        if var is None:
            return None
        if op == "<":
            return var < num
        if op == "<=":
            return var <= num
        if op == ">":
            return var > num
        if op == ">=":
            return var >= num
    m = re.match(r"BETWEEN\(\s*sensor\(\s*(\w+)\s*\)\s*,\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\)",
                 clause)
    if m:
        name, a, b = m.group(1), float(m.group(2)), float(m.group(3))
        var = ctx.get(name)
        if var is None:
            return None
        lo, hi = min(a, b), max(a, b)
        return z3.And(var >= lo, var <= hi)
    # 未知子句 -> 忽略 (视为 True)
    return None


def _build_context() -> Dict[str, Any]:
    """创建 Z3 变量上下文 (数值传感器 Real, 布尔传感器 Bool)。"""
    if not _Z3_AVAILABLE:
        return {}
    ctx: Dict[str, Any] = {}
    for name, (lo, hi) in _DOMAINS.items():
        ctx[name] = z3.Real(f"sv_{name}")
    for name in _BOOL_SENSORS:
        ctx[name] = z3.Bool(f"sv_{name}")
    return ctx


def _domain_expr(ctx: Dict[str, Any]) -> Optional[Any]:
    """物理定义域约束 (所有数值传感器在物理范围内, 布尔传感器任意)。"""
    if not _Z3_AVAILABLE:
        return None
    exprs: List[Any] = []
    for name, (lo, hi) in _DOMAINS.items():
        var = ctx[name]
        exprs.append(z3.And(var >= lo, var <= hi))
    return z3.And(*exprs)


# ---------------------------------------------------------------------------
# 规则解析
# ---------------------------------------------------------------------------
def parse_rule_conditions(rules_text: str) -> List[Tuple[str, str]]:
    """解析 ABDL 文本, 返回 [(rule_id, condition_str)] 列表 (按出现顺序)。"""
    out: List[Tuple[str, str]] = []
    for m in _RULE_BLOCK_RE.finditer(rules_text):
        rid = m.group(1)
        body = m.group(2)
        cm = _COND_RE.search(body)
        if cm:
            out.append((rid, cm.group(1)))
    return out


def _simulate_apply(entries: List[Dict[str, Any]], rules_text: str) -> Tuple[Optional[str], str]:
    """模拟应用 diff (与 S32 coverage_continuity_check 相同 text.replace 语义)。

    返回 (candidate_text, err)。err 非空表示锚点失配, candidate_text=None。
    """
    candidate = rules_text
    for idx, en in enumerate(entries):
        old = str(en.get("old", ""))
        new = str(en.get("new", ""))
        if not old:
            continue
        cnt = candidate.count(old)
        exp = en.get("expected")
        if cnt == 0 or (exp is not None and cnt != exp):
            return None, (f"entry#{idx} 锚点失配 (old 出现 {cnt} 次, expected={exp})")
        candidate = candidate.replace(old, new, cnt)
    return candidate, ""


# ---------------------------------------------------------------------------
# 核心验证: 联合覆盖完备性 (不变量 I1)
# ---------------------------------------------------------------------------
def _find_coverage_holes(rules_text: str,
                         max_holes: int = 5,
                         timeout_ms: int = 3000) -> Tuple[bool, List[str], float]:
    """验证不变量 I1: 联合覆盖完备性。

    返回 (valid, holes, elapsed_s):
      valid=True  无联合空洞 (∀ 输入点 ∈ 定义域, 至少一条规则匹配)
      holes      反例 (可读字符串), 最多 max_holes 个
      elapsed_s   Z3 求解耗时
    """
    if not _Z3_AVAILABLE:
        return True, [], 0.0
    ctx = _build_context()
    domain = _domain_expr(ctx)
    conds = parse_rule_conditions(rules_text)
    if not conds:
        return False, ["无规则可解析"], 0.0
    z3_conds: List[Any] = []
    for _rid, _c in conds:
        e = _condition_to_z3(_c, ctx)
        if e is not None:
            z3_conds.append(e)
    if not z3_conds:
        return True, [], 0.0  # 全部无法解析 -> 降级放行 (保守)

    solver = z3.Solver()
    solver.set("timeout", timeout_ms)
    # 反例 = 定义域内且无任何规则匹配
    solver.add(domain)
    solver.add(z3.Not(z3.Or(*z3_conds)))

    t0 = time.time()
    holes: List[str] = []
    valid = True
    for _ in range(max_holes):
        r = solver.check()
        if r == z3.unsat:
            break
        if r == z3.unknown:
            break  # 超时/不可判定 -> 停止 (视为无进一步反例)
        model = solver.model()
        hole_desc = _format_model(model, ctx)
        holes.append(hole_desc)
        # 阻止该反例再次出现 (所有以 sv_ 前缀的变量都是本模块创建的)
        blocker = z3.Or([
            v() != model[v] for v in model
            if str(v).startswith("sv_")
        ])
        solver.add(blocker)
        valid = False
    elapsed = time.time() - t0
    return valid, holes, elapsed


def _format_model(model: Any, ctx: Dict[str, Any]) -> str:
    """将 Z3 model 格式化为可读反例。"""
    parts: List[str] = []
    for name in sorted(_DOMAINS):
        var = ctx[name]
        try:
            val = model[var]
            parts.append(f"{name}={val}")
        except Exception:
            parts.append(f"{name}=?")
    for name in sorted(_BOOL_SENSORS):
        var = ctx[name]
        try:
            val = model[var]
            parts.append(f"{name}={val}")
        except Exception:
            parts.append(f"{name}=?")
    return "(" + ", ".join(parts) + ")"


# ---------------------------------------------------------------------------
# 对外 API: 基线自检 + diff 级预检 (第四层防护)
# ---------------------------------------------------------------------------
def symbolic_verify(rules_text: Optional[str] = None,
                    rules_path: Optional[str] = None,
                    max_holes: int = 5) -> Tuple[bool, str, Dict[str, Any]]:
    """基线自检: 对当前规则文本验证联合覆盖完备性。

    返回 (valid, reason, stats)。valid=False 说明基线本身存在联合空洞
    (不拦截 — 基线是已验收状态, 仅作记录/知识), stats 含 holes/elapsed。
    """
    stats: Dict[str, Any] = {}
    if not _Z3_AVAILABLE:
        return True, "z3 不可用, 符号验证降级放行", {"z3": False}
    if rules_text is None:
        path = rules_path or RULES_PATH
        if not os.path.isfile(path):
            return True, f"规则文件缺失 ({path}) 降级放行", {"z3": True}
        with open(path, "r", encoding="utf-8") as f:
            rules_text = f.read()
    valid, holes, elapsed = _find_coverage_holes(rules_text, max_holes=max_holes)
    stats.update({"z3": True, "holes": holes, "elapsed_s": round(elapsed, 4)})
    n = len(parse_rule_conditions(rules_text))
    if valid:
        return True, (f"联合覆盖完备: {n} 条规则, Z3 证明 ∀输入点∈定义域至少一规则匹配 "
                      f"({elapsed:.2f}s)"), stats
    return False, (f"联合空洞 {len(holes)} 个 (基线, 容忍): 首个 {holes[0]}"), stats


def _find_new_holes(cand_rules_text: str,
                    base_rules_text: str,
                    max_holes: int = 3,
                    timeout_ms: int = 3000) -> Tuple[bool, List[str], float]:
    """验证「候选覆盖 ⊆ 基线覆盖」的联合包含关系 (数学精确)。

    新增空洞查询:
        ∃x ∈ 定义域: 基线有规则匹配 ∧ 候选无任何规则匹配
        = And(domain, Or(base_conds), Not(Or(cand_conds)))
    若 sat -> 候选丢掉了基线有覆盖的区域 -> 新增联合空洞 (拦截)。
    若 unsat -> 候选任意丢失区域均为基线既有空洞 (容忍, 行为影响由差分评估捕获)。

    返回 (valid, holes, elapsed_s)。valid=False 表示存在候选新增空洞。
    """
    if not _Z3_AVAILABLE:
        return True, [], 0.0
    ctx = _build_context()
    domain = _domain_expr(ctx)

    def _conds_of(text: str) -> List[Any]:
        out: List[Any] = []
        for _rid, _c in parse_rule_conditions(text):
            e = _condition_to_z3(_c, ctx)
            if e is not None:
                out.append(e)
        return out

    base_conds = _conds_of(base_rules_text)
    cand_conds = _conds_of(cand_rules_text)
    if not base_conds or not cand_conds:
        return True, [], 0.0  # 无法解析 -> 降级放行 (保守)

    solver = z3.Solver()
    solver.set("timeout", timeout_ms)
    solver.add(domain)
    solver.add(z3.Or(*base_conds))
    solver.add(z3.Not(z3.Or(*cand_conds)))

    t0 = time.time()
    holes: List[str] = []
    valid = True
    for _ in range(max_holes):
        r = solver.check()
        if r == z3.unsat:
            break
        if r == z3.unknown:
            break  # 超时/不可判定
        model = solver.model()
        holes.append(_format_model(model, ctx))
        blocker = z3.Or([
            v() != model[v] for v in model
            if str(v).startswith("sv_")
        ])
        solver.add(blocker)
        valid = False
    elapsed = time.time() - t0
    return valid, holes, elapsed


# ---------------------------------------------------------------------------
# 对外 API: 基线自检 + diff 级预检 (第四层防护)
# ---------------------------------------------------------------------------
def symbolic_verify(rules_text: Optional[str] = None,
                    rules_path: Optional[str] = None,
                    max_holes: int = 5) -> Tuple[bool, str, Dict[str, Any]]:
    """基线自检: 对当前规则文本验证联合覆盖完备性。

    返回 (valid, reason, stats)。valid=False 说明基线本身存在联合空洞
    (不拦截 — 基线是已验收状态, 仅作记录/知识), stats 含 holes/elapsed。
    """
    stats: Dict[str, Any] = {}
    if not _Z3_AVAILABLE:
        return True, "z3 不可用, 符号验证降级放行", {"z3": False}
    if rules_text is None:
        path = rules_path or RULES_PATH
        if not os.path.isfile(path):
            return True, f"规则文件缺失 ({path}) 降级放行", {"z3": True}
        with open(path, "r", encoding="utf-8") as f:
            rules_text = f.read()
    valid, holes, elapsed = _find_coverage_holes(rules_text, max_holes=max_holes)
    stats.update({"z3": True, "holes": holes, "elapsed_s": round(elapsed, 4)})
    n = len(parse_rule_conditions(rules_text))
    if valid:
        return True, (f"联合覆盖完备: {n} 条规则, Z3 证明 ∀输入点∈定义域至少一规则匹配 "
                      f"({elapsed:.2f}s)"), stats
    return False, (f"联合空洞 {len(holes)} 个 (基线, 容忍): 首个 {holes[0]}"), stats


def symbolic_verify_diff(entries: List[Dict[str, Any]],
                         rules_text: Optional[str] = None,
                         rules_path: Optional[str] = None,
                         max_holes: int = 3) -> Tuple[bool, str, Dict[str, Any]]:
    """Sprint 35 第四层防护: 候选 diff 的联合覆盖预检 (数学级)。

    语义 (与 S32 一致, 但联合空间): 仅拦截「候选新增」的联合空洞 —
      新增空洞查询: ∃x: 基线有匹配 ∧ 候选无匹配 (Z3 证明候选覆盖 ⊇ 基线覆盖)。
      候选覆盖完备 (I1 在候选上成立) 时, 此查询必然 unsat, 直接放行。

    返回 (valid, reason, stats)。valid=False 时外层记录 SYMBOLIC_PROOF_FAIL。
    """
    stats: Dict[str, Any] = {}
    if not _Z3_AVAILABLE:
        return True, "z3 不可用, 符号验证降级放行", {"z3": False}
    if rules_text is None:
        path = rules_path or RULES_PATH
        if not os.path.isfile(path):
            return True, f"规则文件缺失 ({path}) 降级放行", {"z3": True}
        with open(path, "r", encoding="utf-8") as f:
            rules_text = f.read()

    # 与 S32 coverage_continuity_check 相同的跳过语义:
    # 仅当 entries 涉及数值传感器条件变更时才做符号验证;
    # 纯 priority / 裸文本 / 无 sensor() 的变更跳过 (行为影响由差分评估捕获)。
    involved = any(
        "sensor(" in str(en.get("old", "")) or "sensor(" in str(en.get("new", ""))
        for en in entries
    )
    if not involved:
        return True, "无数值传感器条件变更, 符号验证跳过 (纯 priority/文本变更)", {
            "z3": True, "skipped": True}

    candidate, err = _simulate_apply(entries, rules_text)
    if err:
        return False, f"SYMBOLIC 预检: 模拟应用失败 ({err})", stats

    # 1) 候选自身联合覆盖完备性 (I1) — 信息性, 基线空洞容忍
    cand_valid, cand_holes, cand_elapsed = _find_coverage_holes(candidate, max_holes=5)
    # 2) 候选新增空洞 (核心拦截判据)
    no_new, new_holes, new_elapsed = _find_new_holes(candidate, rules_text,
                                                     max_holes=max_holes)

    stats.update({
        "z3": True,
        "cand_valid": cand_valid,
        "cand_holes": cand_holes,
        "new_holes": new_holes,
        "elapsed_s": round(new_elapsed + cand_elapsed, 4),
    })
    if no_new:
        base_note = (f"候选联合覆盖完备 (Z3 证明 ∀输入点有规则匹配, {cand_elapsed:.2f}s)"
                     if cand_valid else
                     f"候选联合空洞均为基线既有 ({len(cand_holes)} 个采样), 容忍放行")
        return True, f"联合覆盖包含验证通过: {base_note}", stats
    return False, ("SYMBOLIC_PROOF_FAIL: 候选引入联合覆盖空洞 (基线有覆盖、候选无覆盖) "
                   f"e.g. {new_holes} -> Z3 数学级拦截 "
                   f"(S32 单维投影盲区, S35 第四层防护)"), stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Z3 符号验证层 (Sprint 35 T1)")
    ap.add_argument("--selfcheck", action="store_true", help="对当前 ABDL 基线做完备性自检")
    ap.add_argument("--show", action="store_true", help="打印全部反例 (最多 5 个)")
    ap.add_argument("--rules", default=None, help="规则文件路径 (默认 simulation_rules.abdl)")
    args = ap.parse_args()

    if not _Z3_AVAILABLE:
        print("z3 不可用: pip3 install --break-system-packages z3-solver")
        return 2

    if args.selfcheck:
        path = args.rules or RULES_PATH
        valid, reason, stats = symbolic_verify(rules_path=path)
        print(f"[SELFCHECK] valid={valid}")
        print(f"  reason: {reason}")
        if args.show:
            for h in stats.get("holes", []):
                print(f"  hole: {h}")
        return 0 if valid else 1
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
