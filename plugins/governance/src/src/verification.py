"""S66 — declaration_only 盲点验证通道 (Verification Channel)。

背景 (S65 VCE 2.0 扫描): 协议网关全部裁决依赖 agent 请求体自我声明
(triggered/satisfied/violation), 恶意 agent 可谎报 satisfied=true 绕过
enforce 升级路径 — 即 `declaration_only` 盲点。

本模块 (CVE-S Phase 3: Governance verifiable):
  - VerificationResult:   验证结果 (可审计, 序列化友好)
  - DeclarationValidator: 验证器协议 (T2 接口)
  - NoopValidator:        默认无验证器 (诚实边界, 不伪称验证能力)
  - BaselineDeclarationValidator: 基线一致性验证器 (T3)
  - LLMSemanticValidator: 语义验证器 (S1 — 审计缺陷修复, 策略 A 插槽落地)

设计原则:
  - 可插拔: 单一协议接口, LLM 语义验证器/签名验证器可作为未来实现插槽
  - 确定性: 基线验证器全部检查为确定性逻辑 (可复现、可测试、可审计)
  - 诚实边界: 基线只做一致性检查, 不声称能证明 agent 真的执行了协议;
    深层语义验证由 LLM 层承担 (见 docs/s66_verification_channel.md)
  - 向后兼容: 无验证器时网关行为与 S65 完全一致

S1 (审计缺陷修复 — LLM 语义验证插槽):
  BaselineDeclarationValidator 仅做确定性一致性检查, 无法识别"锚点存在但
  语义无关"的伪造证据 (如 evidence="passed" 但实际并未执行)。
  LLMSemanticValidator 组合基线 + LLM 语义判断:
    - 基线失败 → 直接采纳 (确定性, 无需 LLM)
    - 基线通过 + LLM 可用 → 语义复核 (拦截语义伪造)
    - 基线通过 + LLM 不可用 → fail-open 回退基线判定 (不阻塞裁决)
"""

import json
import re
import threading
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


# ── LLM 语义验证器 (S1 / 策略 A 插槽) ────────────────────────────────

class LLMSemanticValidator:
    """LLM 语义验证器 (S1 审计缺陷修复 — declaration_only 盲点语义缓解)。

    动机 (审计缺陷 S1): BaselineDeclarationValidator 只能做**确定性一致性**
    检查。攻击者可构造"锚点存在但语义无关"的伪造证据 (如 evidence="passed"
    而实际未执行协议), 绕过基线的零成本谎报拦截 — 这是 declaration_only
    盲点的**语义层**残余。

    本验证器组合策略 (fail-open 优先):
      1. 先跑基线一致性检查 (确定性, 低延迟, 可复现)
      2. 基线失败 → 直接采纳基线结论 (确定性判定优先, 无需 LLM)
      3. 基线通过 (声明有锚点) → 调用注入的 LLM 语义复核
         - LLM 判定语义一致   → verified=True (置信度取基线/LLM 较低者, 保守)
         - LLM 判定语义伪造   → verified=False (降级 → 网关升级为 ESCALATE)
      4. LLM 不可用 (未注入 / 异常 / 超时) → **fail-open**: 回退基线判定,
         verified 保持基线结论 (锚点存在 → 不因 LLM 缺席而误伤合法声明),
         但 reason 标注 "semantic-llm-unavailable" 供审计侧观测。

    注入契约:
      llm_provider: Callable[[dict], dict] — 接收语义上下文 dict, 返回
        {"verified": bool, "confidence": float, "reason": str}
      timeout: 秒 (默认 10.0); 超时视为 LLM 不可用 (fail-open)

    诚实边界: LLM 层不伪称确定性 — 置信度上限受基线约束 (取 min),
    语义结论仅为"降级触发"用途, 不提升放行置信度。
    """

    name = "semantic-llm"

    def __init__(self, llm_provider=None, timeout: float = 10.0,
                 baseline: Optional[BaselineDeclarationValidator] = None):
        self._llm_provider = llm_provider
        self._timeout = timeout
        self._baseline = baseline or BaselineDeclarationValidator()

    # -- 公共接口 -----------------------------------------------------

    def validate(self, rule: Any, path: str, method: str,
                 body: Optional[Dict]) -> VerificationResult:
        base = self._baseline.validate(rule, path, method, body)

        # 1) 基线失败或平凡通过 → 确定性结论优先, 无需 LLM
        if not base.verified or base.claim == "(n/a)":
            return base

        # 2) 基线通过 (有锚点) → 语义复核
        if self._llm_provider is None:
            return self._unavailable(
                base, "未注入 llm_provider — 语义层缺席 (fail-open 回退基线)")

        ctx = self._build_semantic_context(rule, path, method, body, base)
        try:
            verdict = self._call_llm(ctx)
        except Exception as exc:  # 任何异常/超时 → fail-open 回退基线
            return self._unavailable(
                base, f"LLM 调用异常: {exc} — fail-open 回退基线")

        if not isinstance(verdict, dict) or "verified" not in verdict:
            return self._unavailable(
                base, f"LLM 返回畸形结果 {verdict!r} — fail-open 回退基线")

        if verdict.get("verified"):
            return VerificationResult(
                claim=base.claim,
                verified=True,
                confidence=min(base.confidence, float(verdict.get("confidence", 1.0))),
                reason=f"基线锚点 + LLM 语义一致: "
                       f"{verdict.get('reason', '')} (语义复核通过)",
                validator=self.name,
            )
        return VerificationResult(
            claim=base.claim,
            verified=False,
            confidence=float(verdict.get("confidence", 0.6)),
            reason=f"LLM 语义判定声明伪造: "
                   f"{verdict.get('reason', '')} — 锚点存在但语义不支撑 "
                   f"satisfied=true (S1 语义层拦截)",
            validator=self.name,
        )

    # -- 内部逻辑 -----------------------------------------------------

    def _call_llm(self, ctx: Dict) -> dict:
        """调用 LLM provider, 带超时保护 (超时 → fail-open)。"""
        result_box: dict = {}

        def _run() -> None:
            result_box["verdict"] = self._llm_provider(ctx)

        worker = threading.Thread(target=_run, daemon=True)
        worker.start()
        worker.join(timeout=self._timeout)
        if worker.is_alive():
            raise TimeoutError(
                f"LLM provider 超时 ({self._timeout}s)")
        return result_box.get("verdict")

    def _build_semantic_context(self, rule: Any, path: str, method: str,
                                body: Optional[Dict],
                                base: VerificationResult) -> Dict:
        """构造供 LLM 判断的语义上下文 (结构化, 无 prompt 注入面)。"""
        json_path = getattr(rule, "json_path", None) or ""
        module = self._baseline._module_from_path(json_path)
        state = self._baseline._extract_state(body, module)
        return {
            "rule": {
                "name": getattr(rule, "name", "?"),
                "action": getattr(rule, "action", None),
                "json_path": json_path,
                "json_pattern": getattr(rule, "json_pattern", None) or "",
            },
            "request": {"path": path, "method": method},
            "claim": base.claim,
            "protocol_module": module,
            "protocol_state": state,
        }

    def _unavailable(self, base: VerificationResult, why: str) -> VerificationResult:
        """fail-open: 语义层不可用时回退基线判定, 但 reason 显式标注。"""
        return VerificationResult(
            claim=base.claim,
            verified=base.verified,       # 保持基线结论 — 不误伤合法声明
            confidence=base.confidence,
            reason=f"{base.reason} | [semantic-llm-unavailable] {why}",
            validator=self.name,
        )
