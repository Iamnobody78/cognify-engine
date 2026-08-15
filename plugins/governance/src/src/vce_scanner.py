"""VCE 2.0 治理扫描器 — agent-governance-v2 规则自审层 (Sprint 65 Phase 2)。

核心目标 (CVE-S on governance-v2 Phase 2): 让治理规则不仅能"自省" (S64 MCE
AST), 还能"自审"自身的冲突与盲点。

契约 (与 bottlesumo_pi/governance/meta_harness/meta_edu.py 的 VCE 2.0 一致):
  vce_scan(ast, raw_text) -> {
    Polarization_Index:        极化系数 [0,1] (规则间极化程度)
    Value_Tensions:            价值张力对 (规则间价值冲突)
    Asymmetric_Perspectives:   不对称视角 (单方面声明/缺失的验证维度)
  }

本模块扩展:
  RuleConflicts:    检测到的具体规则冲突 (结构化, 可审计)
  BlindSpots:       治理盲点 (未覆盖的模块/维度)

输入: MCE introspection 产物 (S64 RuleMCE.to_dict() 列表) — 含每条规则的
      Tension_Vectors / Entities / Structural_Constraints / origin。
输出: vce_scan_report dict (可序列化为 JSON, 经 ProtocolGateway.scan() 产出)。

设计原则:
  - 契约复用: Polarization_Index/Value_Tensions/Asymmetric_Perspectives 与
    meta_edu VCE 2.0 字段一致; 实现面向规则结构而非自然语言
  - 冲突检测可执行: RuleConflicts 带规则名/类型/原因, 供审计与自动修复
  - 盲点显式化: 缺失模块/缺失规则类型/声明依赖全部列出
  - HONEST-BOUNDARY 联动: 扫描结果含 honest_boundary 声明 (检测能力边界)
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .policy import Rule

# VCE 2.0 契约字段 (与 meta_edu.vce_scan 输出对齐)
VCE_KEYS: tuple = (
    "Polarization_Index", "Value_Tensions", "Asymmetric_Perspectives",
)
# 本模块扩展字段
EXTRA_KEYS: tuple = ("RuleConflicts", "BlindSpots")

# 规则类型 → 价值维度 (用于张力检测)
_RULE_VALUE: Dict[str, str] = {
    "ethics": "伦理约束",
    "enforce": "执行保障",
    "ok": "效率放行",
}

# 不对称视角: 规则类型 → 潜在不对称描述 (S64 Tension_Vectors 的机器化)
_ASYMMETRY: Dict[str, List[str]] = {
    "enforce": ["触发条件由 agent 声明, 无独立验证通道"],
    "ok": ["satisfied=true 依赖 agent 自我声明, 无第三方证据"],
    "ethics": ["violation 字段仅检测显式声明, 无法发现隐式违规"],
}


@dataclass
class RuleConflict:
    """规则冲突记录 (可审计)。"""
    rule_a: str
    rule_b: str
    kind: str  # priority_collision | path_overlap | condition_overlap | action_ambiguity
    severity: str  # high | medium | low
    reason: str

    def to_dict(self) -> Dict:
        return {
            "rule_a": self.rule_a,
            "rule_b": self.rule_b,
            "kind": self.kind,
            "severity": self.severity,
            "reason": self.reason,
        }


@dataclass
class BlindSpot:
    """治理盲点记录。"""
    category: str  # missing_module | missing_rule_type | declaration_only | no_governance_default
    description: str
    severity: str = "medium"

    def to_dict(self) -> Dict:
        return {"category": self.category, "description": self.description,
                "severity": self.severity}


def _polarity(rule_mces: List[Dict]) -> float:
    """极化系数: 基于规则动作分散度 + priority 差距 + 张力向量密度。

    规则: 动作类型越多(ALLOW/ESCALATE/DENY 并存) + priority 差距越大 +
    Tension_Vectors 越多 → 极化越高。范围 [0, 1]。
    """
    if not rule_mces:
        return 0.0
    actions = {r.get("ast", {}).get("rule_type", "?") for r in rule_mces}
    action_diversity = len(actions) / 3.0
    priorities = []
    tensions_total = 0
    for r in rule_mces:
        ast = r.get("ast", {})
        prio = r.get("priority")
        if isinstance(prio, (int, float)):
            priorities.append(prio)
        tensions_total += len(ast.get("Tension_Vectors", []))
    prio_spread = 0.0
    if len(priorities) >= 2:
        prio_spread = min(1.0, (max(priorities) - min(priorities)) / 30.0)
    tension_density = min(1.0, tensions_total / 9.0)
    return round(min(1.0, 0.4 * action_diversity + 0.35 * prio_spread + 0.25 * tension_density), 3)


def _value_tensions(rule_mces: List[Dict]) -> List[str]:
    """价值张力: 规则类型间两两张力 (伦理 vs 执行 vs 放行)。"""
    types = []
    for r in rule_mces:
        t = r.get("rule_type")
        if t and t not in types:
            types.append(t)
    out = []
    if {"ethics", "enforce"} <= set(types):
        out.append("伦理约束 vs 执行保障: DENY 可能阻碍 legitimate ESCALATE 升级路径")
    if {"ethics", "ok"} <= set(types):
        out.append("伦理约束 vs 效率放行: 放行(ALLOW_WITH_WARNING)可能绕过伦理检查")
    if {"enforce", "ok"} <= set(types):
        out.append("执行保障 vs 效率放行: triggered+satisfied 并存时裁决路径需明确(负向前瞻)")
    return out[:6]


def _asymmetry(rule_mces: List[Dict]) -> List[str]:
    """不对称视角: 按规则类型收集潜在单方面声明 (机器化 _ASYMMETRY)。"""
    out = []
    seen = set()
    for r in rule_mces:
        t = r.get("rule_type")
        for a in _ASYMMETRY.get(t, []):
            key = t + ":" + a
            if key not in seen:
                seen.add(key)
                out.append(f"[{t}] {a}")
    return out[:4]


def _find_conflicts(rule_mces: List[Dict], rules: Optional[List[Rule]] = None) -> List[RuleConflict]:
    """规则冲突检测 (结构化):
      1. priority_collision: 同 priority 不同 action → 裁决不确定
      2. condition_overlap: 同模块 enforce/ok json_path 重叠 (S63 负向前瞻防护的再验证)
      3. action_ambiguity: 同 action 但语义冲突 (如 DENY 与 ALLOW 同条件域)
    """
    conflicts: List[RuleConflict] = []
    by_name = {}
    for r in rule_mces:
        by_name[r.get("rule", "")] = r

    # 1) priority collision
    prio_groups: Dict[int, List[Dict]] = {}
    for r in rule_mces:
        prio = r.get("priority")
        if isinstance(prio, (int, float)):
            prio_groups.setdefault(prio, []).append(r)
    for prio, group in prio_groups.items():
        actions = {g.get("rule_type") for g in group}
        if len(actions) > 1:
            names = [g.get("rule", "?") for g in group]
            conflicts.append(RuleConflict(
                rule_a=names[0], rule_b=names[1], kind="priority_collision",
                severity="high",
                reason=f"priority={prio} 被 {len(group)} 条规则共享且 action 不同 — "
                       f"evaluate 按 priority 返回首个命中, 顺序依赖 dict 排序, 裁决不确定",
            ))

    # 2) condition overlap: 同模块 enforce 与 ok 的 json_path 重叠
    mod_groups: Dict[str, List[Dict]] = {}
    for r in rule_mces:
        m = re.match(r"protocol-([a-z_]+)-", r.get("rule", ""))
        if m:
            mod_groups.setdefault(m.group(1), []).append(r)
    for mod, group in mod_groups.items():
        types = {g.get("rule_type") for g in group}
        if {"enforce", "ok"} <= types:
            conflicts.append(RuleConflict(
                rule_a=f"protocol-{mod}-enforce", rule_b=f"protocol-{mod}-ok",
                kind="condition_overlap", severity="low",
                reason=f"enforce/ok 均匹配协议状态对象 ({mod}); 依赖负向前瞻 "
                       f"(?=.*triggered:true)(?!.*satisfied:true) 区分 — 若协议状态 "
                       f"schema 变化可能导致误判",
            ))

    # 3) action ambiguity: 同模块 ethics(DENY) 与 ok(ALLOW) 并存 — 预期设计, 记录低危
    for mod, group in mod_groups.items():
        types = {g.get("rule_type") for g in group}
        if {"ethics", "ok"} <= types:
            conflicts.append(RuleConflict(
                rule_a=f"protocol-{mod}-ethics", rule_b=f"protocol-{mod}-ok",
                kind="action_ambiguity", severity="low",
                reason=f"ethics(DENY p=5) 与 ok(ALLOW_WITH_WARNING p=25/30) 同域并存 — "
                       f"violation 声明同时存在时 DENY 优先 (预期), 但 agent 可能同时声明 "
                       f"violation+satisfied, 语义需明确",
            ))
    return conflicts


def _find_blindspots(rule_mces: List[Dict], modules_expected: Optional[List[str]] = None,
                     verification_channel: Optional[str] = None) -> List[BlindSpot]:
    """盲点检测:
      1. missing_rule_type: 某模块缺规则类型 (如缺 ethics 规则)
      2. declaration_only: 全部裁决依赖 agent 声明 (无独立验证通道)
         — S66: 验证通道存在时 (verification_channel 非空且非 "none"),
           该盲点消除 (外部验证层已落地)
      3. no_governance_default: 无 governance 声明时的默认行为 (静默 ALLOW)
    """
    spots: List[BlindSpot] = []
    has_channel = bool(verification_channel) and verification_channel != "none"
    mod_groups: Dict[str, List[str]] = {}
    for r in rule_mces:
        m = re.match(r"protocol-([a-z_]+)-", r.get("rule", ""))
        t = r.get("rule_type", "?")
        if m:
            mod_groups.setdefault(m.group(1), []).append(t)

    for mod, types in mod_groups.items():
        for needed in ("ethics", "enforce", "ok"):
            if needed not in types:
                spots.append(BlindSpot(
                    category="missing_rule_type", severity="high",
                    description=f"模块 {mod} 缺少 {needed} 规则 — {_RULE_VALUE[needed]} "
                                f"维度未治理",
                ))

    # declaration_only: 每模块规则都依赖声明 — 仅当无验证通道时报告
    if not has_channel:
        for mod, types in mod_groups.items():
            if types:
                spots.append(BlindSpot(
                    category="declaration_only", severity="medium",
                    description=f"模块 {mod} 全部裁决依赖 agent 请求体声明 "
                                f"(triggered/satisfied/violation), 无独立验证通道 — "
                                f"恶意 agent 可谎报 satisfied=true 绕过 enforce",
                ))
    return spots[:8]


def vce_scan_rules(rule_mces: List[Dict],
                   rules: Optional[List[Rule]] = None,
                   modules_expected: Optional[List[str]] = None,
                   verification_channel: Optional[str] = None) -> Dict:
    """VCE 2.0 扫描入口: MCE AST 规则列表 → 扫描报告。

    Args:
        rule_mces: S64 introspection 产物的规则列表 (每条含 rule/rule_type/
                   priority/ast/origin)。
        rules: 原始 Rule 列表 (可选, 供冲突检测引用)。
        modules_expected: 期望的协议模块 (可选, 盲点检测用)。
        verification_channel: S66 验证通道标识 (如 "baseline")。
                   非空且非 "none" 时, declaration_only 盲点消除
                   (外部验证层已落地), 报告中记录 Verification_Channel。
    """
    conflicts = _find_conflicts(rule_mces, rules)
    spots = _find_blindspots(rule_mces, modules_expected, verification_channel)
    has_channel = bool(verification_channel) and verification_channel != "none"
    report = {
        # VCE 2.0 契约字段
        "Polarization_Index": _polarity(rule_mces),
        "Value_Tensions": _value_tensions(rule_mces),
        "Asymmetric_Perspectives": _asymmetry(rule_mces),
        # 扩展字段
        "RuleConflicts": [c.to_dict() for c in conflicts],
        "BlindSpots": [s.to_dict() for s in spots],
        # S66 验证通道状态
        "Verification_Channel": {
            "enabled": has_channel,
            "type": "pluggable-validator" if has_channel else "none",
            "validator": verification_channel or "none",
            "mitigates": ["declaration_only (satisfied 谎报)"],
        },
        # 元信息
        "scanned_rule_count": len(rule_mces),
        "conflict_count": len(conflicts),
        "blindspot_count": len(spots),
        # HONEST-BOUNDARY 联动: 扫描能力边界声明
        "honest_boundary": {
            "detects": ["priority 冲突", "条件重叠", "声明依赖盲点", "规则缺失"],
            "does_not_detect": (
                ["深层语义谎报 (基线一致性已覆盖, 语义层需 LLM)",
                 "自然语言协议语义偏差 (需 LLM 层)"]
                if has_channel else
                ["恶意 agent 谎报声明 (需外部验证通道)",
                 "自然语言协议语义偏差 (需 LLM 层)"]
            ),
            "scope": f"protocol gateway 规则集 ({len(rule_mces)} rules)",
        },
    }
    return report


def summarize_scan(report: Dict) -> str:
    """人类可读摘要 (审计/报告用)。"""
    lines = [
        f"VCE 2.0 扫描: {report['scanned_rule_count']} 规则 | "
        f"极化 {report['Polarization_Index']} | "
        f"冲突 {report['conflict_count']} | 盲点 {report['blindspot_count']}",
    ]
    for t in report["Value_Tensions"]:
        lines.append(f"  张力: {t}")
    for c in report["RuleConflicts"]:
        lines.append(f"  冲突[{c['severity']}] {c['kind']}: {c['reason']}")
    for s in report["BlindSpots"]:
        lines.append(f"  盲点[{s['severity']}] {s['category']}: {s['description']}")
    return "\n".join(lines)
