"""S66 — declaration_only 盲点验证通道 (Verification Channel)。

背景 (S65 VCE 2.0 扫描): 协议网关全部裁决依赖 agent 请求体自我声明
(triggered/satisfied/violation), 恶意 agent 可谎报 satisfied=true 绕过
enforce 升级路径 — 即 `declaration_only` 盲点。

本模块 (CVE-S Phase 3: Governance verifiable):
  - VerificationResult:   验证结果 (可审计, 序列化友好)
  - DeclarationValidator: 验证器协议 (T2 接口)
  - NoopValidator:        默认无验证器 (诚实边界, 不伪称验证能力)
  - BaselineDeclarationValidator: 基线一致性验证器 (T3)

设计原则:
  - 可插拔: 单一协议接口, LLM 语义验证器/签名验证器可作为未来实现插槽
  - 确定性: 基线验证器全部检查为确定性逻辑 (可复现、可测试、可审计)
  - 诚实边界: 基线只做一致性检查, 不声称能证明 agent 真的执行了协议;
    深层语义验证留给 LLM 层 (见 docs/s66_verification_channel.md)
  - 向后兼容: 无验证器时网关行为与 S65 完全一致
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol, runtime_checkable

# ── 验证结果 ─────────────────────────────────────────────────────────

@dataclass
class VerificationResult:
    """单条声明验证结果 (可审计)。"""
    claim: str            # 被验证的声明 (如 "satisfied=true")
    verified: bool        # 验证是否通过
    confidence: float     # 置信度 [0,1]
    reason: str           # 人类可读原因 (审计/报告用)
    validator: str        # 验证器名称

    def to_dict(self) -> Dict:
        return {
            "claim": self.claim,
            "verified": self.verified,
            "confidence": self.confidence,
            "reason": self.reason,
            "validator": self.validator,
        }


# ── 验证器协议 (T2 接口) ─────────────────────────────────────────────

@runtime_checkable
class DeclarationValidator(Protocol):
    """声明验证器协议。

    任何实现必须:
      - 暴露 `name` 属性 (验证器标识, 用于报告/审计)
      - 实现 `validate(rule, path, method, body) -> VerificationResult`

    可插拔设计: BaselineDeclarationValidator (确定性一致性) 为默认基线;
    未来可注入 LLM 语义验证器 / 签名验证器 (见 T1 设计文档策略 A/B)。
    """

    name: str

    def validate(self, rule: Any, path: str, method: str,
                 body: Optional[Dict]) -> VerificationResult:
        """验证规则命中后的声明。

        Args:
            rule: 命中规则 (src.policy.Rule, 含 json_path/json_pattern/action)
            path: 请求路径
            method: HTTP 方法
            body: 请求体 (声明载体)
        Returns:
            VerificationResult: 验证结果
        """
        ...


class NoopValidator:
    """默认无验证器 — 诚实边界。

    不执行任何验证: verified=False, confidence=0。
    网关无验证器时的行为与 S65 完全一致 (action 不降级),
    但报告可标记 channel="none", 供 VCE 扫描识别盲点状态。
    """

    name = "none"

    def validate(self, rule: Any, path: str, method: str,
                 body: Optional[Dict]) -> VerificationResult:
        return VerificationResult(
            claim="(no verification channel configured)",
            verified=False,
            confidence=0.0,
            reason="网关未配置验证器 — 声明未被独立验证 (S65 基线行为)",
            validator=self.name,
        )


# ── 基线验证器 (T3) ──────────────────────────────────────────────────

# 声明相关字段
_SATISFIED = "satisfied"
_TRIGGERED = "triggered"
_VIOLATION = "violation"
# 证据锚点字段 (请求体上下文支撑 satisfied 声明的可检查字段)
_EVIDENCE_KEYS = ("evidence", "output", "result", "proof")


class BaselineDeclarationValidator:
    """基线一致性验证器 (T3 交付)。

    对声明做**确定性一致性检查**, 阻断"零成本谎报":

      1. violation 非空 且 satisfied=true 并存  → 矛盾声明 (verified=False, c=0.95)
      2. satisfied=true 且含非空证据锚点        → 有上下文锚定 (verified=True, c=0.8)
      3. satisfied=true 但无任何证据锚点        → 声明无支撑 (verified=False, c=0.6)
         (declaration_only 盲点缓解主路径)
      4. 协议状态非 dict / 声明字段缺失          → 结构异常 (verified=False, c=0.9)
      5. 规则不依赖 satisfied 声明 (如 ethics)  → 平凡通过 (verified=True, c=1.0)

    诚实边界: 本验证器只做一致性检查, 不证明 agent 真的执行了协议;
    深层语义验证属于 LLM 层 (策略 A 插槽)。
    """

    name = "baseline"

    # -- 公共接口 -----------------------------------------------------

    def validate(self, rule: Any, path: str, method: str,
                 body: Optional[Dict]) -> VerificationResult:
        if not rule:
            return self._trivial("rule 为空 — 无声明可验证")
        json_path = getattr(rule, "json_path", None) or ""
        json_pattern = getattr(rule, "json_pattern", None) or ""
        action = getattr(rule, "action", None)

        # 5) 不依赖 satisfied 声明的规则 (ethics DENY 走 violation, 非声明依赖)
        if not self._is_satisfied_dependent(json_path, json_pattern):
            return self._trivial(
                f"规则 {getattr(rule, 'name', '?')} 不依赖 satisfied 声明 "
                f"(action={action}) — 无可验证的放行声明")

        # 提取协议状态对象
        module = self._module_from_path(json_path)
        state = self._extract_state(body, module)
        if state is None:
            return VerificationResult(
                claim=f"{module}.satisfied",
                verified=False,
                confidence=0.9,
                reason=f"协议状态对象缺失/非 dict (module={module}) — "
                       f"声明无载体, 结构异常",
                validator=self.name,
            )
        if not isinstance(state, dict):
            return VerificationResult(
                claim=f"{module}.satisfied",
                verified=False,
                confidence=0.9,
                reason=f"协议状态对象非 dict (module={module}, "
                       f"type={type(state).__name__}) — 结构异常",
                validator=self.name,
            )

        satisfied = state.get(_SATISFIED, False)
        violation = state.get(_VIOLATION)
        if not satisfied:
            # 未声明满足 → 无放行声明可验证 (enforce 升级路径不受影响)
            return self._trivial(
                f"规则 {getattr(rule, 'name', '?')} 未声明 satisfied=true — "
                f"无可验证的放行声明")

        # 1) 矛盾声明: violation 非空 + satisfied=true
        if violation:
            return VerificationResult(
                claim=f"{module}.satisfied=true (含 violation={violation!r})",
                verified=False,
                confidence=0.95,
                reason="violation 非空与 satisfied=true 并存 — 矛盾声明 "
                       "(DENY 与 ALLOW 条件同时成立, S65 action_ambiguity "
                       "冲突的验证层落地)",
                validator=self.name,
            )

        # 2/3) 证据锚点检查
        anchors = self._find_evidence_anchors(state)
        if anchors:
            return VerificationResult(
                claim=f"{module}.satisfied=true",
                verified=True,
                confidence=0.8,
                reason=f"声明有上下文锚定: 证据字段 {anchors} 非空 — "
                       f"satisfied 声明与请求体上下文一致",
                validator=self.name,
            )
        return VerificationResult(
            claim=f"{module}.satisfied=true",
            verified=False,
            confidence=0.6,
            reason=f"声明无上下文锚点: satisfied=true 但协议状态 "
                   f"({module}) 不含任何非空证据字段 {list(_EVIDENCE_KEYS)} "
                   f"— 零成本谎报风险 (declaration_only 缓解主路径)",
            validator=self.name,
        )

    # -- 内部逻辑 -----------------------------------------------------

    def _is_satisfied_dependent(self, json_path: str, json_pattern: str) -> bool:
        """规则是否依赖 satisfied 声明 (ok/enforce 规则)。"""
        return _SATISFIED in json_pattern or _SATISFIED in json_path

    def _module_from_path(self, json_path: str) -> str:
        m = re.search(r"protocols\.([a-z_]+)", json_path)
        return m.group(1) if m else "unknown"

    def _extract_state(self, body: Optional[Dict], module: str) -> Any:
        """从请求体提取协议状态对象 (容忍 None/非 dict)。"""
        if not isinstance(body, dict):
            return None
        governance = body.get("governance")
        if not isinstance(governance, dict):
            return None
        protocols = governance.get("protocols")
        if not isinstance(protocols, dict):
            return None
        return protocols.get(module)

    def _find_evidence_anchors(self, state: Dict) -> list:
        """查找非空证据锚点字段 (evidence/output/result/proof)。"""
        anchors = []
        for key in _EVIDENCE_KEYS:
            val = state.get(key)
            if val is not None and val != "" and val != [] and val != {}:
                anchors.append(key)
        return anchors

    def _trivial(self, reason: str) -> VerificationResult:
        return VerificationResult(
            claim="(n/a)",
            verified=True,
            confidence=1.0,
            reason=reason,
            validator=self.name,
        )
