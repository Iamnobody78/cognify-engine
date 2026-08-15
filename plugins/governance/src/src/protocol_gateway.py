"""Protocol Gateway — 协议编译器 (S62 A1) 产物接入规则引擎的可执行桥。

核心目标 (Sprint 63): 让 bottlesumo_pi/governance/protocols/schema/*.yaml
(11 列声明式协议) 产出的治理规则不再停留在 YAML, 而是能被 agent-governance-v2
的 PolicyEngine 自动执行。

架构:
  协议 YAML (声明式)  →  ProtocolGateway.compile_rules()  →  Rule 列表
                                                              ↓
  请求体 governance 声明 ── 触发 ──>  PolicyEngine.evaluate()  执行

协议语义 → 规则语义映射 (每个协议编译为 3 条规则):
  1. protocol-{module}-enforce : 协议状态对象含 triggered=true 且无 satisfied=true
                                  (触发但未满足) → ESCALATE
  2. protocol-{module}-ethics   : 声明违反伦理边界 (violation 非空) → DENY
  3. protocol-{module}-ok       : 声明已满足 (satisfied=true) → ALLOW_WITH_WARNING

  priority: DENY(5) < enforce(20/15) < ok(30/25) — evaluate() 按 priority
  升序返回首个命中; 违反伦理先于触发升级, 触发先于放行。enforce/ok 均匹配
  整个协议状态对象 (紧凑 JSON) 用正/负向前瞻区分 triggered/satisfied 并存。

请求体协议状态声明 schema (代理在请求中携带治理上下文):
  {
    "governance": {
      "protocols": {
        "feynman_test":    {"triggered": true, "satisfied": false},
        "logic_chain_check": {"violation": "攻击人格"}
      }
    }
  }

fail-closed: 协议文件缺失/字段缺失/空目录 → 拒绝加载 (启动即报错);
  sync 脚本从 bottlesumo_pi 编译器产物复制, 校验 12 必需字段。
"""

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import yaml

from .policy import Rule
from .verification import (
    DeclarationValidator,
    NoopValidator,
    VerificationResult,
)

logger = logging.getLogger(__name__)

# ── S62 A1 编译器契约: 11 列协议必需字段 ─────────────────────────────
REQUIRED_FIELDS: tuple = (
    "module", "category", "level", "core_purpose", "metacognitive_q",
    "collab_directive", "trigger", "ethics_boundary", "source",
    "frequency", "strategy", "expected_output",
)
VALID_LEVELS: tuple = ("L2", "L3")

# 默认协议目录: 与仓库自包含 (git 提交, sync 脚本维护), 不依赖跨 repo 运行时路径
DEFAULT_PROTOCOLS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "protocols"
)

# level → priority 映射: L3 (高风险) 触发优先级更高 (更早拦截)
_ENFORCE_PRIORITY = {"L2": 20, "L3": 15}
_OK_PRIORITY = {"L2": 30, "L3": 25}
_ETHICS_PRIORITY = 5  # 伦理边界违反最优先 (DENY)


# ── 协议加载与校验 ──────────────────────────────────────────────────
@dataclass
class Protocol:
    """编译自 11 列协议 YAML 的结构化协议 (校验后)。"""
    module: str
    category: str
    level: str
    core_purpose: str
    metacognitive_q: str
    collab_directive: str
    trigger: str
    ethics_boundary: str
    source: str
    frequency: str
    strategy: str
    expected_output: str
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_yaml(cls, path: str) -> "Protocol":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"protocol {path}: YAML root must be a mapping")
        if data.get("schema_version") != "11-col-v1":
            raise ValueError(
                f"protocol {path}: schema_version must be '11-col-v1' "
                f"(fail-closed) — got {data.get('schema_version')!r}"
            )
        proto = data.get("protocol")
        if not isinstance(proto, dict):
            raise ValueError(f"protocol {path}: missing 'protocol' mapping (fail-closed)")
        missing = [f for f in REQUIRED_FIELDS if f not in proto]
        if missing:
            raise ValueError(
                f"protocol {path}: missing required fields {missing} (fail-closed)"
            )
        level = str(proto["level"]).upper()
        if level not in VALID_LEVELS:
            raise ValueError(
                f"protocol {path}: invalid level {proto['level']!r} — "
                f"must be one of {VALID_LEVELS} (fail-closed)"
            )
        return cls(
            module=str(proto["module"]).strip(),
            category=str(proto["category"]).strip(),
            level=level,
            core_purpose=str(proto["core_purpose"]).strip(),
            metacognitive_q=str(proto["metacognitive_q"]).strip(),
            collab_directive=str(proto["collab_directive"]).strip(),
            trigger=str(proto["trigger"]).strip(),
            ethics_boundary=str(proto["ethics_boundary"]).strip(),
            source=str(proto["source"]).strip(),
            frequency=str(proto["frequency"]).strip(),
            strategy=str(proto["strategy"]).strip(),
            expected_output=str(proto["expected_output"]).strip(),
            raw=data,
        )


def load_protocols(protocols_dir: Optional[str] = None) -> List[Protocol]:
    """加载目录下所有 11 列协议 YAML (fail-closed: 缺失/空目录/坏文件拒绝)。"""
    d = protocols_dir or DEFAULT_PROTOCOLS_DIR
    if not os.path.isdir(d):
        raise FileNotFoundError(
            f"protocols dir not found: {d} (fail-closed — set protocols_dir or "
            f"sync config/protocols from bottlesumo_pi protocol compiler)"
        )
    files = sorted(
        p for p in os.listdir(d)
        if p.endswith(".yaml") or p.endswith(".yml")
    )
    if not files:
        raise ValueError(f"protocols dir {d} has no YAML files (fail-closed)")
    out = []
    for fn in files:
        p = os.path.join(d, fn)
        try:
            proto = Protocol.from_yaml(p)
        except Exception as e:  # noqa: BLE001 — 任何解析失败都拒绝 (fail-closed)
            raise ValueError(f"failed to load protocol {fn}: {e} (fail-closed)") from e
        out.append(proto)
    # module 唯一性 (防重复编译导致规则名冲突)
    seen = {}
    for proto in out:
        if proto.module in seen:
            raise ValueError(
                f"duplicate protocol module {proto.module!r} in "
                f"{seen[proto.module]} and {proto.module} (fail-closed)"
            )
        seen[proto.module] = os.path.basename(proto.source or "")
    return out


# ── 协议 → 规则编译 ─────────────────────────────────────────────────
def compile_protocol_rules(protocols: List[Protocol]) -> List[Rule]:
    """每个协议编译为 3 条可执行规则 (enforce / ethics / ok)。

    规则条件基于请求体的 governance 协议状态声明:
      $.governance.protocols.{module}.triggered  = true   → 协议被触发
      $.governance.protocols.{module}.satisfied  = true   → 协议已满足
      $.governance.protocols.{module}.violation  = <str>  → 伦理违规声明

    path_pattern="*" + method=None: 协议规则在任意路径/方法上评估, 但仅当
    json_path 提取到对应声明才命中 (无声明 → 不命中 → 对现有流量零影响)。
    """
    rules: List[Rule] = []
    for p in protocols:
        base = f"$.governance.protocols.{p.module}"
        # 1) 触发但未满足 → ESCALATE。
        #    边界: 对协议状态对象 (紧凑 JSON) 匹配 — 要求 triggered=true 且
        #    无 satisfied=true (负向前瞻), 避免 triggered+satisfied 并存时误报。
        rules.append(Rule(
            name=f"protocol-{p.module}-enforce",
            path_pattern="*",
            action="ESCALATE",
            priority=_ENFORCE_PRIORITY.get(p.level, 20),
            reason=(
                f"协议 {p.module} 已触发 ({p.trigger}); 需满足产出 "
                f"'{p.expected_output}' 并声明 satisfied=true (collab: {p.collab_directive})"
            ),
            json_path=base,
            json_pattern=r'(?=.*"triggered":true)(?!.*"satisfied":true)',
            escalation_timeout=300,
            escalation_channel="protocol_gateway",
        ))
        # 2) 伦理边界违反 → DENY (最优先)
        rules.append(Rule(
            name=f"protocol-{p.module}-ethics",
            path_pattern="*",
            action="DENY",
            priority=_ETHICS_PRIORITY,
            reason=(
                f"协议 {p.module} 伦理边界被违反: {p.ethics_boundary} "
                f"(violation 声明非空 → DENY)"
            ),
            json_path=f"{base}.violation",
            json_pattern=r".+",
        ))
        # 3) 声明满足 → 放行但记录 (ALLOW_WITH_WARNING)
        rules.append(Rule(
            name=f"protocol-{p.module}-ok",
            path_pattern="*",
            action="ALLOW_WITH_WARNING",
            priority=_OK_PRIORITY.get(p.level, 30),
            reason=f"协议 {p.module} 已满足: {p.expected_output}",
            json_path=base,
            json_pattern=r'(?=.*"satisfied":true)',
        ))
    rules.sort(key=lambda r: r.priority)
    return rules


def generate_policy_yaml(rules: List[Rule]) -> dict:
    """编译产物 → PolicyEngine 可直接加载的策略 dict (声明式数据, 非硬编码)。"""
    rule_data = []
    for r in rules:
        d = {
            "name": r.name,
            "path_pattern": r.path_pattern,
            "action": r.action,
            "reason": r.reason,
            "priority": r.priority,
            "escalation_timeout": r.escalation_timeout,
            "escalation_channel": r.escalation_channel,
        }
        if r.method is not None:
            d["method"] = r.method
        if r.json_path is not None:
            d["json_path"] = r.json_path
        if r.json_pattern is not None:
            d["json_pattern"] = r.json_pattern
        rule_data.append(d)
    return {
        "name": "protocol-gateway",
        "version": "0.1.0",
        "source": "compiled from bottlesumo_pi/governance/protocols/schema "
                  "(S62 A1 protocol compiler) via src/protocol_gateway.py",
        "rules": rule_data,
    }


# ── 网关执行器 ─────────────────────────────────────────────────────
@dataclass
class ProtocolGateway:
    """协议网关: 加载协议 → 编译规则 → 与 PolicyEngine 兼容执行。

    与 PolicyEngine 组合使用:
      gw = ProtocolGateway()
      engine = PolicyEngine("config/policies.yaml")
      engine.rules = sorted(engine.rules + gw.rules, key=lambda r: r.priority)
      engine._jp_index = JsonPathIndex(engine.rules)   # 重建索引
    或直接用 gw.evaluate(...) 做协议层独立裁决 (返回 Rule 或 None)。
    """
    protocols: List[Protocol] = field(default_factory=list)
    rules: List[Rule] = field(default_factory=list)

    def __init__(self, protocols_dir: Optional[str] = None,
                 validator: Optional[DeclarationValidator] = None,
                 audit_sink: Optional[Callable[[dict], None]] = None):
        self.protocols = load_protocols(protocols_dir)
        self.rules = compile_protocol_rules(self.protocols)
        # S66 验证通道: 默认 NoopValidator (诚实边界, 无验证器时行为与 S65 一致)
        self.validator: DeclarationValidator = validator or NoopValidator()
        # S68 审计回调: 每次 evaluate_verified 完成后调用 audit_sink(event_dict)。
        # 引擎层独立可审计 — 任何消费方 (dashboard/合规日志/webhook) 可注入。
        self.audit_sink: Optional[Callable[[dict], None]] = audit_sink

    @property
    def modules(self) -> List[str]:
        return [p.module for p in self.protocols]

    def evaluate(self, path: str, method: str, body=None) -> Optional[Rule]:
        """协议层独立裁决: 按 priority 返回首个命中规则 (与 PolicyEngine 语义一致)。"""
        for rule in self.rules:
            if rule.matches(path, method, body):
                return rule
        return None

    # -- S66 验证通道 (CVE-S Phase 3: Governance verifiable) -----------

    def set_validator(self, validator: DeclarationValidator) -> None:
        """热切换验证器 (可插拔: baseline / LLM 语义 / 签名实现均实现同一协议)。"""
        self.validator = validator

    def verify_declaration(self, rule: Rule, path: str, method: str,
                           body=None) -> VerificationResult:
        """对命中规则的声明执行外部验证 (调用注入的验证器)。

        无验证器时返回 NoopValidator 结果 (verified=False, confidence=0),
        网关裁决行为不受影响 (向后兼容)。
        """
        return self.validator.validate(rule, path, method, body)

    def evaluate_verified(self, path: str, method: str, body=None) -> dict:
        """S66: 裁决 + 声明验证合一。

        返回:
          {
            "rule": 命中规则名或 None,
            "action": 最终动作 (验证失败时 ok 规则降级为 ESCALATE),
            "verification": VerificationResult.to_dict() 或 None,
            "channel": 验证器名称,
          }

        谎报缓解语义:
          - 命中 ok (ALLOW_WITH_WARNING) 且声明验证失败 → action 降级为
            ESCALATE (声明不可信 → 升级复核), 这是 declaration_only 盲点
            缓解主路径;
          - 命中 enforce (已升级) / ethics (DENY) → action 不变,
            验证结果附加为信息;
          - NoopValidator (未配置) → 验证结果 verified=False/confidence=0
            但 action 不降级 (保持 S65 行为, 向后兼容)。
        """
        rule = self.evaluate(path, method, body)
        if rule is None:
            return {"rule": None, "action": None,
                    "verification": None, "channel": self.validator.name}
        res = self.verify_declaration(rule, path, method, body)
        action = rule.action
        if rule.action == "ALLOW_WITH_WARNING" and not res.verified \
                and self.validator.name != "none":
            # 放行声明未通过独立验证 → 降级为升级复核 (谎报缓解)
            action = "ESCALATE"
        out = {
            "rule": rule.name,
            "action": action,
            "verification": res.to_dict(),
            "channel": self.validator.name,
        }
        # S68 审计回调: 引擎层独立审计链 (不阻塞裁决路径)
        if self.audit_sink is not None:
            try:
                self.audit_sink({
                    **out,
                    "path": path,
                    "method": method,
                    "body": body,
                })
            except Exception as exc:  # 审计失败不得影响治理裁决 (fail-open 审计, 但需可观测 — AUDIT-0073)
                logger.warning("audit_sink 回调失败 (fail-open, 不阻塞裁决): %s", exc)
        return out

    def to_policy_yaml(self) -> dict:
        return generate_policy_yaml(self.rules)

    def introspect(self) -> dict:
        """S64 Phase 1: MCE 2.0 自省 — 每条规则可回答"我为什么存在、我在治理什么"。

        返回可审计的自省产物 (序列化为 dict, 供 JSON/YAML 归档):
          { protocol_module: [RuleMCE.to_dict(), ...], ... }
        """
        from .mce_introspection import build_mce_introspection
        intro = build_mce_introspection(self.protocols, self.rules)
        return {
            "version": "MCE-2.0",
            "protocols": {pms.protocol_module: [rmc.to_dict() for rmc in pms.rule_mces]
                          for pms in intro},
        }

    def scan(self) -> dict:
        """S65 Phase 2: VCE 2.0 扫描 — 治理规则"自审"冲突与盲点。

        消费 MCE 自省产物 (introspect), 检测规则间极化/冲突/盲点。
        返回可审计的扫描报告 (序列化为 dict, 供 vce_scan_report.json 归档):
          { Polarization_Index, Value_Tensions, Asymmetric_Perspectives,
            RuleConflicts, BlindSpots, honest_boundary, ... }
        """
        from .vce_scanner import vce_scan_rules
        intro = self.introspect()
        rule_mces = []
        for mod, rmcs in intro["protocols"].items():
            rule_mces.extend(rmcs)
        return vce_scan_rules(rule_mces, rules=self.rules,
                              modules_expected=self.modules,
                              verification_channel=self.validator.name)

    def verify(self) -> dict:
        """完整性自检: 返回协议/规则统计 (RULE-NOTION-003: verify 必须计算全部产物)。"""
        return {
            "protocol_count": len(self.protocols),
            "rule_count": len(self.rules),
            "modules": self.modules,
            "per_module_rules": {
                p.module: [r.name for r in self.rules if r.name.startswith(f"protocol-{p.module}-")]
                for p in self.protocols
            },
            "expected_rule_count": len(self.protocols) * 3,
        }
