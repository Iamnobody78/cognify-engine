"""MCE 2.0 元认知编译 — agent-governance-v2 规则自省层 (Sprint 64 Phase 1)。

核心目标 (CVE-S on governance-v2 Phase 1): 让治理规则能回答
"我为什么存在、我在治理什么" —— 将 S63 协议网关编译出的可执行规则
升级为"可自省的规则"。

契约 (与 bottlesumo_pi/governance/meta_harness/meta_edu.py 的 MCE 2.0 一致):
  mce_compile(input) -> AST {
    Core_Directive:       核心指令 (规则存在的根本原因)
    Entities:             治理对象实体 (从协议字段提取)
    Structural_Constraints:结构约束 (触发/边界/产出要求)
    Tension_Vectors:      张力向量 (规则间的潜在冲突)
    Entropy_Score:        熵值 (规则复杂度/信息量)
  }

本模块不重复实现 meta_edu 的通用编译 (该实现面向自然语言输入), 而是
为 agent-governance-v2 提供**面向治理规则的结构化编译**: 输入是 S63
编译产出的 Rule (含协议语义字段), 输出是该规则的可自省 AST。

设计原则:
  - 自包含: 不依赖 bottlesumo_pi 运行时 (跨仓库解耦), 契约字段兼容
  - 溯源: 每条规则 AST 携带 origin (协议 module + 规则类型 + 上游协议字段)
  - 可审计: AST 可序列化为 dict/YAML, 供审计与版本化
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .policy import Rule

# MCE 2.0 AST 契约字段 (与 meta_edu.mce_compile 输出对齐)
AST_KEYS: tuple = (
    "Core_Directive", "Entities", "Structural_Constraints",
    "Tension_Vectors", "Entropy_Score",
)

# 规则类型 → 治理语义 (rule 存在的"为什么")
_RULE_WHY: Dict[str, str] = {
    "ethics": "伦理边界守卫: 防止治理对象违反协议伦理约束 (violation → DENY)",
    "enforce": "触发执行: 协议被触发但未满足产出时升级为人工/自动验证 (ESCALATE)",
    "ok": "放行记录: 协议已满足时放行但留痕 (ALLOW_WITH_WARNING)",
}


def _extract_entities(*texts: str) -> List[str]:
    """从协议文本提取实体 (大写 token / 长标识符, 与 meta_edu 启发式一致)。"""
    entities = []
    seen = set()
    for text in texts:
        for m in re.finditer(r"([A-Z][A-Z0-9-]{2,}|[a-z_]{4,})", text or ""):
            token = m.group(1)
            key = token.upper()
            if key not in seen:
                seen.add(key)
                entities.append(token)
    return entities[:12]


def _entropy_score(entities: List[str], constraint_count: int) -> float:
    """信息熵: 基于实体多样性与约束数量 (范围 [0.1, 0.9], 与 meta_edu 一致)。"""
    e = len(set(entities)) / 24.0 + constraint_count / 12.0
    return round(min(0.9, max(0.1, e)), 3)


@dataclass
class RuleMCE:
    """单条规则的可自省 AST (MCE 2.0 编译产物)。"""
    rule: Rule
    protocol_module: str
    rule_type: str  # ethics | enforce | ok
    trigger_text: str
    ethics_boundary: str
    expected_output: str
    level: str
    core_purpose: str
    ast: Dict = field(default_factory=dict, repr=False)

    def compile(self) -> Dict:
        """执行 MCE 2.0 编译 → AST。"""
        entities = _extract_entities(
            self.trigger_text, self.ethics_boundary, self.expected_output,
            self.protocol_module,
        )
        constraints = [c for c in (
            f"trigger: {self.trigger_text}" if self.trigger_text else None,
            f"ethics: {self.ethics_boundary}" if self.ethics_boundary else None,
            f"output: {self.expected_output}" if self.expected_output else None,
        ) if c]
        self.ast = {
            "Core_Directive": (
                f"{_RULE_WHY.get(self.rule_type, '治理规则')} | "
                f"协议 {self.protocol_module} [{self.level}] | 规则 {self.rule.name}"
            ),
            "Entities": entities,
            "Structural_Constraints": constraints,
            "Tension_Vectors": self._tensions(),
            "Entropy_Score": _entropy_score(entities, len(constraints)),
        }
        return self.ast

    def _tensions(self) -> List[str]:
        """张力向量: 规则类型内部的潜在冲突 (自省核心)。"""
        t = []
        if self.rule_type == "enforce":
            t.append("enforce vs ok: triggered+satisfied 并存时不得误报 ESCALATE "
                     "(负向前瞻已防)")
        if self.rule_type == "ethics":
            t.append("ethics 优先于 enforce/ok: DENY(priority 5) 必须压过业务规则")
        if self.rule_type == "ok":
            t.append("ok 放行依赖 agent 声明 satisfied=true, 存在声明即满足的风险")
        return t

    # ── 自省接口: 规则反问"我为什么存在、我在治理什么" ──────────────
    def why_exists(self) -> str:
        if not self.ast:
            self.compile()
        return str(self.ast["Core_Directive"])

    def what_it_governs(self) -> List[str]:
        if not self.ast:
            self.compile()
        return list(self.ast["Entities"])

    def constraints(self) -> List[str]:
        if not self.ast:
            self.compile()
        return list(self.ast["Structural_Constraints"])

    def to_dict(self) -> Dict:
        if not self.ast:
            self.compile()
        return {
            "rule": self.rule.name,
            "protocol_module": self.protocol_module,
            "rule_type": self.rule_type,
            "level": self.level,
            "origin": {
                "trigger": self.trigger_text,
                "ethics_boundary": self.ethics_boundary,
                "expected_output": self.expected_output,
                "core_purpose": self.core_purpose,
            },
            "ast": self.ast,
        }


@dataclass
class ProtocolMCE:
    """协议级自省容器: 一个协议的全部规则 AST + 汇总。"""
    protocol_module: str
    rule_mces: List[RuleMCE] = field(default_factory=list)

    def compile_all(self) -> Dict:
        return {rmc.rule.name: rmc.compile() for rmc in self.rule_mces}

    def summary(self) -> Dict:
        return {
            "protocol_module": self.protocol_module,
            "rule_count": len(self.rule_mces),
            "rule_types": [rmc.rule_type for rmc in self.rule_mces],
            "entities": sorted({
                e for rmc in self.rule_mces
                for e in rmc.what_it_governs()
            }),
            "why_exists": [rmc.why_exists() for rmc in self.rule_mces],
        }


def build_mce_introspection(protocols, rules) -> List[ProtocolMCE]:
    """从协议 + 编译规则构建完整自省层 (S63 产物 → S64 自省)。

    Args:
        protocols: List[Protocol] (S63 protocol_gateway.Protocol)
        rules: List[Rule] (compile_protocol_rules 产物)
    """
    rule_type_by_name = {}
    for name in ("ethics", "enforce", "ok"):
        rule_type_by_name[name] = name
    by_module: Dict[str, List[Rule]] = {}
    for r in rules:
        m = re.match(r"protocol-([a-z_]+)-(ethics|enforce|ok)$", r.name)
        if m:
            by_module.setdefault(m.group(1), []).append(r)

    proto_map = {p.module: p for p in protocols}
    result = []
    for module, prules in sorted(by_module.items()):
        p = proto_map.get(module)
        rms = []
        for r in prules:
            m = re.match(r"protocol-[a-z_]+-(ethics|enforce|ok)$", r.name)
            rtype = m.group(1) if m else "enforce"
            rms.append(RuleMCE(
                rule=r,
                protocol_module=module,
                rule_type=rtype,
                trigger_text=p.trigger if p else "",
                ethics_boundary=p.ethics_boundary if p else "",
                expected_output=p.expected_output if p else "",
                level=p.level if p else "L2",
                core_purpose=p.core_purpose if p else "",
            ))
        result.append(ProtocolMCE(module, rms))
    return result
