"""Governance Gateway — aiohttp Sidecar proxy with policy enforcement.

Usage:
    python -m src.main
    # Starts on port 9000. Point your Agent client at localhost:9000/v1/intercept.
"""

import asyncio
import json
import logging
import os
import time
import traceback
import uuid
from typing import Optional

from aiohttp import web, ClientSession, ClientTimeout

from .models import InterceptRequest, InterceptResponse, DecisionRecord, Verdict
# v1.42.4-step2b (AUDIT-0068): Ls 权重表迁移 YAML — 热重载与 policy 同模式
from .lethality import lethality_for_tool, maybe_reload_lethality
from .policy import PolicyEngine, Rule, _json_extract
from .storage import Storage
from .revoke import revoke_registry  # P1 (暗雷区): 异步弱监督撤销注册表
from . import context_hmac  # TASK-REAL-012 Phase 5: Context Hook HMAC（防头伪造）
from .auth import TenantAuth, load_auth_or_none  # P6: 服务身份认证 + 多租户隔离
# v1.42.1-step2 (可解释主控 Step 2): 元认知观察层接线 —
# 决策轨迹 (CoT) 回放写入 decision_meta.cot, 与主审计链解耦 (独立表, fail-soft)。
from .metacognition.observer import MetacognitionObserver

logger = logging.getLogger(__name__)

# ── configurable constants ──────────────────────────────────────────
INTERCEPT_TIMEOUT = 0.5       # seconds — if policy eval exceeds this, fail-closed
CIRCUIT_BREAKER_LIMIT = 10    # consecutive ESCALATE without resolution → DENY (fail-closed)
CIRCUIT_COOLDOWN_SECONDS = 30.0  # breaker trip cooldown window (DEBT-0001)
AGENT_BACKEND_URL = "http://localhost:8000"   # upstream Agent (for proxy mode)

# DEBT-0018: 网关层请求/响应 body 上限 — 默认 10MB, env 可覆盖。
# 请求侧超限 → 413 拒绝 (fail-closed, DENY 落库可审计); 响应侧超限 →
# 截断 + 标记 (不拒绝合法长响应)。函数形式延迟读 env, 测试可 monkeypatch。
def _max_body_bytes() -> int:
    return int(os.environ.get("GOV_MAX_BODY_BYTES", 10 * 1024 * 1024))

def _max_resp_bytes() -> int:
    return int(os.environ.get("GOV_MAX_RESP_BYTES", 10 * 1024 * 1024))
SHUTDOWN_FLUSH_TIMEOUT = 8  # DEBT-0015: independent cap for shutdown flush; must stay < shutdown_timeout=10
MAX_TRACE_ID_LEN = 128  # TASK-REAL-011.1 (Critic-Security): trace 头值长度上限（超长视为缺失）

# ── v1.42.1-step2 (可解释主控 Step 2): 元认知观察层 ──────────────────
# 全局 observer; create_app 内由 GOV_META_DB env 实例化 (None = 不接线, 与
# SEMANTIC_HOOK_ENABLED 同 opt-in 模式)。所有决策分支在 storage.save 后
# fail-soft 调用 record(cot=...), 观察层异常绝不阻断主路径。
meta_observer: Optional[MetacognitionObserver] = None
COT_MAX_CHARS = 4000  # CoT 链有界截断上限 (防超大 JSON 撑爆 decision_meta)


def _build_cot(*, method: str, path: str, matched_rule: Optional[str],
               verdict: str, reason: Optional[str] = None,
               trace_id: Optional[str] = None,
               tool_name: Optional[str] = None,
               tool_lethality: Optional[float] = None) -> str:
    """构建 CoT 决策轨迹回放 (JSON 字符串, 有界)。

    诚实可审计原则: 只记录真实发生的事件序列 (request 特征 → policy 命中 →
    附加闸门 → 最终裁决), 不做 LLM 事后解释。写入 decision_meta.cot 供
    trace/审计追踪: 用户可以复现"为什么这样判"。
    """
    steps = [
        {"t": "request", "method": method, "path": path,
         "tool": tool_name, "lethality": tool_lethality},
        {"t": "policy", "matched_rule": matched_rule or None,
         "action": verdict},
    ]
    if reason:
        steps.append({"t": "reason", "text": reason[:500]})
    if trace_id:
        steps.append({"t": "trace", "trace_id": trace_id})
    steps.append({"t": "verdict", "verdict": verdict})
    chain = json.dumps(steps, ensure_ascii=False, separators=(",", ":"))
    return chain[:COT_MAX_CHARS]


async def _record_meta_soft(decision: DecisionRecord, *, method: str,
                            path: str, matched_rule: Optional[str],
                            trace_id: Optional[str], reason: Optional[str],
                            tool_name: Optional[str] = None,
                            tool_lethality: Optional[float] = None) -> None:
    """fail-soft 接线: observer 未启用 (None) 或任何异常 → 仅 warning。

    与 semantic_output_audit_async 同契约: 观察层绝不影响网关主路径。
    """
    if meta_observer is None:
        return
    try:
        cot = _build_cot(method=method, path=path, matched_rule=matched_rule,
                         verdict=decision.verdict.value, reason=reason,
                         trace_id=trace_id, tool_name=tool_name,
                         tool_lethality=tool_lethality)
        await asyncio.to_thread(
            meta_observer.record,
            decision_id=decision.id, path=path,
            verdict=decision.verdict.value, trace_id=trace_id,
            method=method, matched_rule=matched_rule, cot=cot)
    except Exception as exc:  # noqa: BLE001 — fail-soft: 观察层异常绝不外泄
        logger.warning("metacognition: record failed (fail-soft): %s", exc)


def _signed_trace_headers(trace_id: str, span_id: str) -> dict:
    """构造响应 trace 头并附加 HMAC 签名（Phase 5）。

    未启用 CONTEXT_HMAC_KEY 时 sign_headers 返回空 dict —— 响应头与
    v0.5.0 完全一致（向后兼容）；启用后下游可验证治理头未被篡改。
    """
    hdrs = {"X-Trace-ID": trace_id, "X-Span-ID": span_id}
    hdrs.update(context_hmac.sign_headers(hdrs))
    return hdrs

# Shared heuristic constants — single source of truth moved to src/danger.py (DEBT-0002)
from .danger import DANGEROUS_PREFIXES, DANGEROUS_METHODS, is_dangerous as _is_dangerous

# TASK-REAL-009 (A-phase): semantic bypass hook — external LLM-Judge, opt-in.
from .semantic_hook import (extract_prompt, is_enabled as semantic_hook_enabled,
                            semantic_hook, semantic_audit_async,
                            extract_code_snippets, semantic_code_audit_async,
                            record_prompt, semantic_context_drift_async,
                            extract_agent_response, semantic_output_audit_async,
                            AGENT_RESPONSE_MAX_CHARS)

# Only these headers are forwarded to the upstream backend (never Authorization)
FORWARD_HEADER_WHITELIST = ("content-type", "accept", "user-agent", "x-agent-id")

# ── global state ────────────────────────────────────────────────────
start_time = time.time()
escalate_count_since_resolve = 0
last_escalate_time = 0.0
breaker_tripped_until = 0.0  # DEBT-0001: deny-all until this timestamp after trip
_escalate_lock: asyncio.Lock = None  # guards escalate_count_since_resolve / last_escalate_time
policy_engine: Optional[PolicyEngine] = None
storage: Optional[Storage] = None
auth: Optional[TenantAuth] = None  # P6: None=兼容模式 (v1.13.0 行为); 注入后启用认证


def _uptime() -> float:
    return time.time() - start_time


# ── handlers ────────────────────────────────────────────────────────

def _trace_context(headers) -> tuple:
    """TASK-REAL-011 (C 阶段): 提取/生成 Trace 因果上下文。

    返回 (trace_id, parent_span_id):
      - trace_id:       X-Trace-ID 头; 缺失 → 新 UUID (本请求开启新调用链)。
      - parent_span_id: X-Parent-Span-ID 头; 缺失 → None (链根节点, 递归 CTE
                        锚点)。当前请求自身的 span_id == decision.id (判定后
                        生成), 通过响应头 X-Span-ID 回传, 下游请求携带
                        X-Parent-Span-ID 指向它即形成因果链。
    设计裁决: 用户确认表"若无 X-Parent-Span-ID 则生成"落地为"生成新链根
    语义"——随机占位 UUID 无法被 CTE 锚定 (parent 必须指向真实父决策 id),
    None 才是唯一自洽的根标记 (详见 docs/trace_report.md §3)。
    """
    # TASK-REAL-012 Phase 5 (Context Hook HMAC): 启用时验证治理头签名。
    #   - None（未启用）      → 兼容模式，按 v0.5.0 逻辑提取（现状不变）
    #   - ("", "")（伪造/缺失签名）→ 降级为新链根（伪造头永不进入审计链）
    #   - (trace_id, parent) → 可信上下文，沿用（仍过长度 fail-safe）
    signed = context_hmac.validate_trace_headers(dict(headers))
    if signed is None:
        trace_id = headers.get("X-Trace-ID") or str(uuid.uuid4())
        parent_span_id = headers.get("X-Parent-Span-ID") or None
    elif signed == ("", ""):
        trace_id = str(uuid.uuid4())  # 伪造头 → 隔离为孤立根节点
        parent_span_id = None
    else:
        trace_id, parent_span_id = signed
    # TASK-REAL-011.1 (Critic-Security): 超长头值拒绝持久化 — 防止索引膨胀/
    # 存储滥用。>MAX_TRACE_ID_LEN 视为缺失 (fail-safe): trace_id → 新链根,
    # parent_span_id → None (根锚点)。截断会破坏链引用, 拒绝/降级为缺失是
    # 唯一不引入悬空引用的语义。
    if len(trace_id) > MAX_TRACE_ID_LEN:
        trace_id = str(uuid.uuid4())
    if parent_span_id is not None and len(parent_span_id) > MAX_TRACE_ID_LEN:
        parent_span_id = None
    return trace_id, parent_span_id


def _auth_gate(request):
    """P6 (外部评审缺口 #1): 网关第一道门 — 认证 + 租户一致性。

    auth 未启用 (None) → 直接放行 (兼容模式, v1.13.0 行为, 391 回归保障)。
    返回 (tenant_id, None) 放行; 或 (None, 401/403 json response) 拒绝。
    - 401: 缺失/无效 API key
    - 403: X-Tenant-ID 与认证身份不符 (跨租户冒称)
    """
    if auth is None:
        return None, None
    tenant_id, err = auth.resolve_tenant(request)
    if err is not None:
        return None, web.json_response(
            {"error": err["error"], "detail": err["detail"]},
            status=err["status"],
        )
    return tenant_id, None


async def intercept_handler(request: web.Request) -> web.Response:
    global escalate_count_since_resolve, last_escalate_time, breaker_tripped_until

    # P6: 网关第一道门 — 身份认证先于一切 (未认证请求不进入治理/审计链)
    tenant_id, auth_resp = _auth_gate(request)
    if auth_resp is not None:
        return auth_resp

    try:
        # DEBT-0018: 显式 body 上限 — content-length 快速拒绝 + 受控读取兜底
        # (aiohttp 3.9+ 移除了 request.json(max_size=...), 改在读取层控制)。
        # 超限 → 413 拒绝 (fail-closed) 并落库, 不再无界读入内存。
        _limit = _max_body_bytes()
        _clen = request.content_length
        if _clen is not None and _clen > _limit:
            return await _oversize_deny(request)
        _raw = await request.content.read(_limit + 1)
        if len(_raw) > _limit:
            return await _oversize_deny(request)
        data = json.loads(_raw)
    except json.JSONDecodeError:
        return web.json_response(
            {"error": "invalid JSON"}, status=400
        )

    try:
        req = InterceptRequest(**data)
    except Exception as e:  # noqa: BLE001 — Pydantic validation error (client-side)
        logger.warning("invalid intercept body (422): %s", e)
        logger.debug("invalid intercept body traceback:\n%s", traceback.format_exc())
        return web.json_response(
            {"error": "invalid request body"}, status=422
        )

    # TASK-REAL-011 (C): 入口处提取 Trace 上下文 — 贯穿本请求全部决策分支
    trace_id, parent_span_id = _trace_context(request.headers)

    # 0. hot-reload policies if YAML changed (DEBT-0005)
    await asyncio.to_thread(policy_engine.maybe_reload)
    # 0a. v1.42.4-step2b: Ls 权重表热重载 (mtime 门控, 失败保留旧表 fail-safe)
    await asyncio.to_thread(maybe_reload_lethality)
    # 1. evaluate policy with timeout guard
    #    TASK-REAL-010 (B): req.body 传入 — json_path 条件规则检查请求体 JSON
    try:
        rule = await asyncio.wait_for(
            asyncio.to_thread(policy_engine.evaluate, req.path, req.method, req.body, tenant_id),
            timeout=INTERCEPT_TIMEOUT,
        )
    except asyncio.TimeoutError:
        # timeout → fail-closed for dangerous operations, escalate for others
        # (v0.1.0 had fail-open: auto-ALLOW. CRITIQUE_V2.md #1 fixed this.)
        if _is_dangerous(req.path, req.method):
            verdict = Verdict.DENY
            reason = "策略评估超时，高风险操作默认拒绝 (fail-closed)"
        else:
            verdict = Verdict.ESCALATE
            reason = "策略评估超时，升级人工审批 (fail-closed)"
        matched_rule = None
        logger.warning("policy evaluation timed out for %s %s → %s", req.method, req.path, verdict.value)
    else:
        # 2. determine verdict from matched rule
        if rule is None:
            verdict = Verdict.ALLOW
            reason = "无匹配策略，默认放行"
            matched_rule = None
        else:
            matched_rule = rule.name
            if rule.action == "DENY":
                verdict = Verdict.DENY
                reason = rule.reason or f"匹配规则 '{rule.name}' → 拦截"
            elif rule.action == "ESCALATE":
                now = time.time()
                async with _escalate_lock:
                    if now < breaker_tripped_until:
                        # DEBT-0001: cooldown window — deny everything until cooldown expires
                        verdict = Verdict.DENY
                        reason = f"熔断冷却中 ({breaker_tripped_until - now:.0f}s 后恢复)，拒绝 (fail-closed)"
                    else:
                        escalate_count_since_resolve += 1
                        last_escalate_time = now
                        if escalate_count_since_resolve >= CIRCUIT_BREAKER_LIMIT:
                            # v0.2.0 (AUDIT-0005): breaker trips to DENY, NOT ALLOW.
                            # DEBT-0001: trip starts a cooldown window; counter resets but
                            # the cooldown prevents immediate re-accumulation.
                            breaker_tripped_until = now + CIRCUIT_COOLDOWN_SECONDS
                            escalate_count_since_resolve = 0
                            await asyncio.to_thread(
                                storage.save_breaker_state,
                                escalate_count_since_resolve,
                                last_escalate_time,
                                breaker_tripped_until,
                            )
                            verdict = Verdict.DENY
                            reason = f"连续 {CIRCUIT_BREAKER_LIMIT} 次升级未获审批，熔断拒绝 (fail-closed)"
                        else:
                            verdict = Verdict.ESCALATE
                            reason = rule.reason or f"匹配规则 '{rule.name}' → 升级人工审批"
            else:
                # TASK-REAL-012 Phase 4 (治理大脑 Phase 1): 五级响应 — ALLOW /
                # ALLOW_WITH_WARNING / SUSPEND 分支。既有 ALLOW 语义不变。
                if rule.action == "ALLOW_WITH_WARNING":
                    verdict = Verdict.ALLOW_WITH_WARNING
                    reason = rule.reason or f"匹配规则 '{rule.name}' → 放行但警告"
                elif rule.action == "SUSPEND":
                    verdict = Verdict.SUSPEND
                    reason = rule.reason or f"匹配规则 '{rule.name}' → 挂起审查"
                else:
                    verdict = Verdict.ALLOW
                    reason = rule.reason or f"匹配规则 '{rule.name}' → 放行"
                # successful ALLOW(-family) = request resolved → reset circuit breaker
                async with _escalate_lock:
                    escalate_count_since_resolve = 0
                    last_escalate_time = 0.0
                    breaker_tripped_until = 0.0
                await asyncio.to_thread(
                    storage.save_breaker_state,
                    escalate_count_since_resolve,
                    last_escalate_time,
                    breaker_tripped_until,
                )

    # 2.4 P1 (暗雷区) 撤销检查: 后台语义审计已判定高风险并撤销该 trace →
    # 后续请求短路 SUSPEND（403 挂起待人工复审）。静态 DENY 优先保留
    # （撤销不覆盖更严厉的规则裁决）。撤销原因随 SUSPEND 决策落库（可审计）。
    if verdict != Verdict.DENY and revoke_registry.is_revoked(trace_id):
        verdict = Verdict.SUSPEND
        reason = (revoke_registry.reason_for(trace_id)
                  or "该 trace 已被语义审计撤销 (高风险)")
        matched_rule = matched_rule or "revoked-trace"

    # 2.5 semantic bypass hook (TASK-REAL-009 / A-phase): the static verdict may
    # be upgraded to ESCALATE by the external LLM-Judge — NEVER downgraded
    # (DENY stays final). Fail-soft: judge down/timeout -> verdict unchanged.
    # P1 (暗雷区): 异步弱监督 — 主链路不再 await judge（消除 +150ms 阻塞）。
    # 后台审计高风险 → 撤销 trace 链（后续请求短路 SUSPEND，见入口检查）。
    if verdict != Verdict.DENY and semantic_hook_enabled():
        _prompt = extract_prompt(req.body)
        # Step 3 (v1.42.2-step3, 可解释主控): 上下文漂移检测 —
        # record_prompt 推当前轮进窗口; 漂移任务在 decision 落库后启动
        # (下方 save 后, 需要 decision.id 供 on_drift 追加 CoT)。
        record_prompt(req.agent_id, _prompt)
        # ML 集成 Phase 1' (裁决 2026-08-04): AST 放行的代码片段也过语义复查 —
        # AST 语法安全但意图危险 (编码混淆/跨函数数据流) 的片段由 LLM-Judge
        # 按红线 A/C 判定, 高风险撤销 trace。
        # v1.42.3-step4: 两项语义审计任务移出 hook 块 → decision 落库后启动
        # (需要 decision.id 供 on_semantic 追加 semantic_judge 到 CoT)。
        _code = extract_code_snippets(req.body)

    # 3. persist decision (strong-typed model, serialized at DB edge)
    _tname, _tleth = _audit_tool_fields(req)
    # TASK-REAL-012 Phase 4 (治理大脑 Phase 1): rationale 可解释字段 —
    # 记录"为什么这么判"（匹配规则 + 语义旁路说明），审计可复核。
    _rationale = (f"rule={matched_rule}" if matched_rule else "no-rule(default-allow)")
    decision = DecisionRecord(
        id=str(uuid.uuid4()),
        verdict=verdict,
        reason=reason,
        matched_rule=matched_rule,
        path=req.path,
        method=req.method,
        agent_id=req.agent_id,
        tool_name=_tname,
        tool_lethality=_tleth,
        trace_id=trace_id,
        parent_span_id=parent_span_id,
        rationale=_rationale,
    )
    # v0.2.2 (external critique #3.1): sqlite3 writes are synchronous — run in
    # the thread pool so the event loop is not blocked (Storage has an internal
    # threading.Lock to serialize access to the shared connection).
    await asyncio.to_thread(storage.save, decision.model_dump(mode="json"))
    # v1.42.1-step2: CoT 决策轨迹回放 → decision_meta.cot (fail-soft)
    await _record_meta_soft(decision, method=req.method, path=req.path,
                            matched_rule=matched_rule, trace_id=trace_id,
                            reason=reason, tool_name=_tname,
                            tool_lethality=_tleth)
    # v1.42.2-step3 + v1.42.3-step4 (可解释主控): 后台审计任务统一在
    # decision 落库后启动 — decision.id 此时已存在, on_drift / on_semantic
    # 回调把 context_drift / semantic_judge 事件追加到该决策的 CoT 轨迹
    # (均幂等, fail-soft)。完整可解释链:
    # request → policy → semantic_judge → context_drift → verdict。
    if verdict != Verdict.DENY and semantic_hook_enabled():
        _on_semantic = (meta_observer.append_semantic
                        if meta_observer is not None else None)
        asyncio.create_task(semantic_context_drift_async(
            trace_id=trace_id, agent_id=req.agent_id,
            user_prompt=_prompt, decision_id=decision.id,
            base_reason=reason,
            on_drift=(meta_observer.append_drift
                      if meta_observer is not None else None)))
        asyncio.create_task(semantic_audit_async(
            trace_id=trace_id, user_prompt=_prompt, base_reason=reason,
            decision_id=decision.id, on_semantic=_on_semantic))
        if _code:
            asyncio.create_task(semantic_code_audit_async(
                trace_id=trace_id, code_snippets=_code, base_reason=reason,
                decision_id=decision.id, on_semantic=_on_semantic))

    # 4. if ALLOW(-family) and proxy mode → forward to upstream Agent
    response_body = None
    if verdict in (Verdict.ALLOW, Verdict.ALLOW_WITH_WARNING) and AGENT_BACKEND_URL:
        response_body = await _proxy_forward(
            req, trace_id,
            decision_id=decision.id,
            on_semantic=(meta_observer.append_semantic
                         if meta_observer is not None else None))

    # 5. build response — TASK-REAL-011: 回传 trace 上下文供下游链接
    #    (span_id == decision.id; 下游用 X-Parent-Span-ID 指向它)
    resp = InterceptResponse(
        verdict=verdict,
        reason=reason,
        decision_id=decision.id,
        matched_rule=matched_rule,
        trace_id=trace_id,
    )
    _trace_headers = _signed_trace_headers(trace_id, decision.id)
    # TASK-REAL-012 Phase 4 (治理大脑 Phase 1): 五级响应输出 —
    # ALLOW_WITH_WARNING → 200 + X-Governance-Warning 头（可观测警告）;
    # SUSPEND → 403（挂起审查，语义区别于 DENY）。
    if verdict == Verdict.DENY:
        return web.json_response(resp.model_dump(mode="json"), status=403, headers=_trace_headers)
    elif verdict == Verdict.ESCALATE:
        return web.json_response(resp.model_dump(mode="json"), status=202, headers=_trace_headers)
    elif verdict == Verdict.SUSPEND:
        return web.json_response(resp.model_dump(mode="json"), status=403, headers=_trace_headers)
    else:
        result = resp.model_dump(mode="json")
        if response_body:
            result["upstream_response"] = response_body
        _resp_headers = dict(_trace_headers)
        if verdict == Verdict.ALLOW_WITH_WARNING:
            _resp_headers["X-Governance-Warning"] = reason
        return web.json_response(result, status=200, headers=_resp_headers)


async def _proxy_forward(req: InterceptRequest, trace_id: Optional[str] = None,
                         decision_id: Optional[str] = None,
                         on_semantic=None) -> Optional[dict]:
    """Forward the request to the upstream Agent backend.

    v0.2.0 (AUDIT-0005): only whitelisted headers are forwarded.
    Authorization / cookies are NEVER proxied upstream.
    """
    try:
        async with ClientSession(timeout=ClientTimeout(total=0.5, connect=0.3)) as session:
            # body may be a parsed dict (InterceptRequest.body) or raw JSON str
            body = req.body
            if isinstance(body, str) and body.strip():
                body = json.loads(body)
            async with session.request(
                method=req.method,
                url=f"{AGENT_BACKEND_URL}{req.path}",
                headers={
                    k: v for k, v in req.headers.items()
                    if k.lower() in FORWARD_HEADER_WHITELIST
                },
                json=body,
            ) as resp:
                # DEBT-0018: 响应侧受控读取 — 超限截断 (不拒绝合法长响应),
                # 截断时返回体携带 truncated 标记供审计消费。
                _limit = _max_resp_bytes()
                _raw = await resp.content.read(_limit + 1)
                _truncated = len(_raw) > _limit
                if _truncated:
                    _raw = _raw[:_limit]
                text = _raw.decode("utf-8", errors="replace")
                # DEBT-0020: 代理转发响应同样异步补判 (与 chat 路径同构)
                # v1.42.3-step4: 附带 decision_id + on_semantic → Judge 裁决
                # 以 semantic_judge 事件追加到该决策的 CoT 轨迹。
                if semantic_hook_enabled() and trace_id:
                    asyncio.create_task(semantic_output_audit_async(
                        trace_id, text, base_reason="proxy-forward",
                        decision_id=decision_id, on_semantic=on_semantic))
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"status": resp.status, "body": text[:1000], "truncated": _truncated}
    except Exception as e:
        logger.warning("proxy forward failed: %s", e)
        logger.debug("proxy forward traceback:\n%s", traceback.format_exc())
        return None


async def health_handler(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "ok",
        "version": "0.4.0",
        "uptime_seconds": round(_uptime(), 2),
        "decisions_total": storage.count(),
    })


async def decisions_handler(request: web.Request) -> web.Response:
    # P6: 审计查询端点受身份门保护 (未认证 → 401)
    _, auth_resp = _auth_gate(request)
    if auth_resp is not None:
        return auth_resp
    limit = int(request.query.get("limit", 50))
    decisions = storage.get_recent(limit)
    return web.json_response({"total": len(decisions), "decisions": decisions})


async def trace_handler(request: web.Request) -> web.Response:
    """TASK-REAL-011 (C): GET /v1/trace/{trace_id} — 返回整条因果调用树。

    递归 CTE (storage.get_trace) 按 depth+timestamp 排序; 节点含杀伤半径
    审计字段 (tool_lethality) 作为边权重, 审计人员可快速定位"哪一步引入
    最大风险"。trace 不存在 → 404 (诚实语义: 资源不存在)。
    """
    # P6: 因果链查询端点受身份门保护 (未认证 → 401)
    _, auth_resp = _auth_gate(request)
    if auth_resp is not None:
        return auth_resp
    trace_id = request.match_info["trace_id"]
    # TASK-REAL-011.1 (Critic-Security): URL 超长 trace_id 无 DB 风险 (参数化
    # 查询 + 无匹配即空), 但拒绝无意义的大查询 — 与 _trace_context 的
    # MAX_TRACE_ID_LEN 上限保持一致。
    if len(trace_id) > MAX_TRACE_ID_LEN:
        return web.json_response({"error": "trace_id too long"}, status=404)
    nodes = await asyncio.to_thread(storage.get_trace, trace_id)
    if not nodes:
        return web.json_response({"error": f"trace {trace_id} not found"}, status=404)
    return web.json_response({"trace_id": trace_id, "node_count": len(nodes), "nodes": nodes})


async def metrics_handler(request: web.Request) -> web.Response:
    """GET /metrics — Prometheus 文本格式暴露运行指标 (阶段 C1 前置)。

    指标全部来自真实运行时状态:
      - governance_uptime_seconds           进程存活时长 (gauge)
      - governance_decisions_total          已落库裁决总数 (counter, 含历史)
      - governance_escalations_since_resolve 自上次熔断重置以来 ESCALATE 计数
      - governance_breaker_tripped          熔断器当前是否打开 (1/0)
      - governance_breaker_remaining_seconds 熔断器剩余锁定秒数 (0=未熔断)
      - governance_ast_languages            ASTGuard 已加载语言 (label 数量)
      - governance_pending_flush            待落库缓冲条目 (运维水位)
    暴露于 /metrics (无认证, 供 Prometheus 抓取; 不包含任何请求体/决策明细)。
    """
    global policy_engine, storage, escalate_count_since_resolve, breaker_tripped_until
    now = time.time()
    remaining = max(0.0, breaker_tripped_until - now)
    ast_langs = 0
    if policy_engine is not None and getattr(policy_engine, "ast_guard", None) is not None:
        ast_langs = len(getattr(policy_engine.ast_guard, "loaded_languages", []))
    lines = [
        "# HELP governance_uptime_seconds Process uptime in seconds.",
        "# TYPE governance_uptime_seconds gauge",
        f"governance_uptime_seconds {_uptime():.3f}",
        "# HELP governance_decisions_total Total decisions persisted to storage.",
        "# TYPE governance_decisions_total counter",
        f"governance_decisions_total {storage.count() if storage else 0}",
        "# HELP governance_escalations_since_resolve ESCALATE count since last breaker reset.",
        "# TYPE governance_escalations_since_resolve gauge",
        f"governance_escalations_since_resolve {escalate_count_since_resolve}",
        "# HELP governance_breaker_tripped Whether the circuit breaker is open.",
        "# TYPE governance_breaker_tripped gauge",
        f"governance_breaker_tripped {1 if breaker_tripped_until > now else 0}",
        "# HELP governance_breaker_remaining_seconds Seconds until breaker auto-resets.",
        "# TYPE governance_breaker_remaining_seconds gauge",
        f"governance_breaker_remaining_seconds {remaining:.3f}",
        "# HELP governance_ast_languages Number of languages loaded in ASTGuard.",
        "# TYPE governance_ast_languages gauge",
        f"governance_ast_languages {ast_langs}",
        "# HELP governance_pending_flush Buffered decisions awaiting flush.",
        "# TYPE governance_pending_flush gauge",
        f"governance_pending_flush {storage.pending_count() if storage else 0}",
    ]
    return web.Response(text="\n".join(lines) + "\n", content_type="text/plain; version=0.0.4")


# ── OpenAI-compatible endpoint (B1: LangChain zero-touch integration) ─

# Tools whose invocation must be blocked at the LLM request level.
# LangChain exposes them as JSON functions inside the request body;
# the gateway inspects tool_calls/tools before forwarding.
# NOTE (AUDIT-0008, Reviewer REJECT fix): names are compared casefolded +
# NFKC-normalized on BOTH sides, so 'Delete_File', 'delete_fιle' (U+03B9)
# and fullwidth variants cannot bypass the exact-match blacklist.
DANGEROUS_TOOL_NAMES = ("delete_file", "delete_user", "sudo_exec", "rm_file")

# TASK-REAL-010: 归一化管线移入 src/norm.py (单一事实源) — lethality 表与
# 本模块共享同一 NFKC -> confusable map -> casefold 流程。
from .norm import norm_tool_name as _norm_tool_name


def _extract_tool_names(req: InterceptRequest) -> list:
    """Extract tool/function names from an OpenAI-format chat request.

    Type-confusion hardened (Reviewer fix): 'tools' / 'messages' /
    'tool_calls' are REQUIRED to be lists; dict bodies yield zero names
    and are treated as undecodable → the handler's fail-closed path
    takes over. Function values must be dicts, names must be strings.
    """
    body = req.body
    if isinstance(body, str) and body.strip():
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            return []
    if not isinstance(body, dict):
        return []
    names = []
    tools = body.get("tools")
    if isinstance(tools, list):
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            fn = tool.get("function")
            if isinstance(fn, dict):            # must be dict, not str
                name = fn.get("name")
                if isinstance(name, str) and name:
                    names.append(name)
    messages = body.get("messages")
    if isinstance(messages, list):
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            tc = msg.get("tool_calls")
            if isinstance(tc, list):
                for call in tc:
                    if not isinstance(call, dict):
                        continue
                    fn = call.get("function")
                    if isinstance(fn, dict):    # must be dict, not str
                        name = fn.get("name")
                        if isinstance(name, str) and name:
                            names.append(name)
    return names


def _audit_tool_fields(req, tool_names=None) -> tuple:
    """TASK-REAL-010 (Step 1): (tool_name, tool_lethality) 审计字段。

    取请求中"杀伤半径最高"的工具名与 Ls (src/lethality.py) — 审计字段反映
    最大风险工具而非第一个遇到的名字, 供事后归因。先走精确的 OpenAI 格式
    提取; 无结果时退化为 json_path 通配提取 ($..name), 覆盖非 OpenAI
    结构化体 (如 /v1/intercept 的任意 agent 请求)。无工具声明 → (None, None)。
    """
    if tool_names is None:
        tool_names = _extract_tool_names(req)
    if not tool_names:
        body = req.body
        if isinstance(body, str) and body.strip():
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                body = None
        if isinstance(body, dict):
            tool_names = [v for v in _json_extract(body, "$..name") if v.strip()]
    if not tool_names:
        return None, None
    worst = max(tool_names, key=lambda n: lethality_for_tool(n))
    return worst, lethality_for_tool(worst)


def _malformed_tool_declaration(req) -> str | None:
    """Detect tool declarations that are present but structurally invalid.

    Fail-closed principle: a declaration we CANNOT verify must never be
    silently ignored and forwarded — a lenient upstream parser may still
    execute it, bypassing governance. Returns an error description or None.

    Reviewer finding R1/R3/R4 extension: 'tools' as dict, 'function' as
    string, non-str 'name' all previously produced an EMPTY name list ->
    treated as ordinary chat -> forwarded upstream. That is a bypass, not
    a crash fix. Malformed declarations must reject the request outright.
    """
    body = req.body
    if isinstance(body, str) and body.strip():
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            return None  # JSON errors are handled by the caller
    if not isinstance(body, dict):
        return None  # no declaration to inspect

    tools = body.get("tools")
    if tools is not None and not isinstance(tools, list):
        return "field 'tools' must be a list"
    if isinstance(tools, list):
        for i, tool in enumerate(tools):
            if not isinstance(tool, dict):
                return f"tools[{i}] must be an object"
            fn = tool.get("function")
            if fn is not None and not isinstance(fn, dict):
                return f"tools[{i}].function must be an object"
            if isinstance(fn, dict):
                name = fn.get("name")
                if name is not None and not isinstance(name, str):
                    return f"tools[{i}].function.name must be a string"

    messages = body.get("messages")
    if messages is not None and not isinstance(messages, list):
        return "field 'messages' must be a list"
    if isinstance(messages, list):
        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                continue  # non-object messages are skipped, not tool decls
            tc = msg.get("tool_calls")
            if tc is not None and not isinstance(tc, list):
                return f"messages[{i}].tool_calls must be a list"
            if isinstance(tc, list):
                for j, call in enumerate(tc):
                    if not isinstance(call, dict):
                        return f"messages[{i}].tool_calls[{j}] must be an object"
                    fn = call.get("function")
                    if fn is not None and not isinstance(fn, dict):
                        return f"messages[{i}].tool_calls[{j}].function must be an object"
                    if isinstance(fn, dict):
                        name = fn.get("name")
                        if name is not None and not isinstance(name, str):
                            return f"messages[{i}].tool_calls[{j}].function.name must be a string"
    return None


async def _deny_decision(req, reason, status, matched_rule, tool_name=None, tool_lethality=None,
                         trace_id=None, parent_span_id=None, rationale=None) -> web.Response:
    """Record a DENY decision and return the gateway rejection response.

    Shared by the malformed-declaration path and the dangerous-tool path
    so persistence + error shape stay identical. tool_name / tool_lethality
    (TASK-REAL-010 Step 1) audit the highest-lethality tool in the request.
    trace_id / parent_span_id (TASK-REAL-011.1, Critic-Security): 所有决策
    分支必须携带 trace 上下文 — 否则该 DENY 决策脱离调用链 (无法被
    GET /v1/trace/{trace_id} 追到), 破坏 C 阶段"全部决策在链上"承诺。
    """
    decision = DecisionRecord(
        id=str(uuid.uuid4()),
        verdict=Verdict.DENY,
        reason=reason,
        matched_rule=matched_rule,
        path=req.path,
        method=req.method,
        agent_id=req.agent_id,
        tool_name=tool_name,
        tool_lethality=tool_lethality,
        trace_id=trace_id,
        parent_span_id=parent_span_id,
        rationale=rationale or f"rule={matched_rule}",
    )
    # v0.2.2 (external critique #3.1): sqlite3 writes are synchronous — run in
    # the thread pool so the event loop is not blocked (Storage has an internal
    # threading.Lock to serialize access to the shared connection).
    await asyncio.to_thread(storage.save, decision.model_dump(mode="json"))
    # v1.42.1-step2: CoT 决策轨迹回放 → decision_meta.cot (fail-soft)
    await _record_meta_soft(decision, method=req.method, path=req.path,
                            matched_rule=matched_rule, trace_id=trace_id,
                            reason=reason, tool_name=tool_name,
                            tool_lethality=tool_lethality)
    _trace_headers = _signed_trace_headers(trace_id, decision.id)
    return web.json_response(
        {
            "error": {
                "message": reason,
                "type": "governance_denied",
                "decision_id": decision.id,
            }
        },
        status=status,
        headers=_trace_headers,
    )


async def _oversize_deny(request: web.Request) -> web.Response:
    """DEBT-0018: 请求体超限 → 413 拒绝 (fail-closed) + DENY 落库 (可审计)。

    统一 intercept / chat 两个入口的超限拒绝行为: trace 上下文从 header
    提取 (body 未解析, 无法从 body 取), 保证超限决策同样在调用链上。
    状态码用 413 (协议语义准确), 与 malformed-declaration 走 400 的
    先例一致 — 非 403 状态码同样落库 DENY, 保持"全部决策在链上"。
    """
    trace_id, parent_span_id = _trace_context(request.headers)
    req = InterceptRequest(
        path=request.path,
        method=request.method,
        headers={k: v for k, v in request.headers.items()},
        body=None,
        agent_id=request.headers.get("x-agent-id"),
    )
    return await _deny_decision(
        req,
        reason=f"请求体超过上限 {_max_body_bytes()} bytes — 拒绝 (fail-closed)",
        status=413,
        matched_rule="body-too-large",
        trace_id=trace_id,
        parent_span_id=parent_span_id,
    )


async def chat_completions_handler(request: web.Request) -> web.Response:
    """OpenAI-compatible /v1/chat/completions.

    Sidecar mode for LangChain/AutoGen: the Agent sets base_url to the
    gateway and talks normal OpenAI protocol — zero code changes. The
    gateway inspects the request (tools + tool_calls) against governance
    policy BEFORE forwarding upstream.
    """
    # P6: 网关第一道门 — 身份认证先于一切 (chat 入口与 intercept 同等保护)
    tenant_id, auth_resp = _auth_gate(request)
    if auth_resp is not None:
        return auth_resp
    # TASK-REAL-011.1 (Critic-Security/DEBT-0022): 入口处提取 Trace 上下文 —
    # chat 路径全部决策分支 (malformed DENY / dangerous DENY / 主路径) 必须
    # 携带 trace_id/parent_span_id, 否则多 Agent 链跨端点断链。
    trace_id, parent_span_id = _trace_context(request.headers)
    try:
        # DEBT-0018: 网关层请求体上限 — content-length 快速拒绝 + 受控读取
        # 兜底 (chunked / 无长度 body 同样覆盖)。超限 → 413 拒绝 (fail-closed,
        # 落库可审计), 不再无界读入内存。
        _limit = _max_body_bytes()
        _clen = request.content_length
        if _clen is not None and _clen > _limit:
            return await _oversize_deny(request)
        raw = await request.content.read(_limit + 1)
        if len(raw) > _limit:
            return await _oversize_deny(request)
        body = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        return web.json_response(
            {"error": {"message": "invalid JSON body", "type": "invalid_request_error"}},
            status=400,
        )

    req = InterceptRequest(
        path="/v1/chat/completions",
        method="POST",
        headers={k: v for k, v in request.headers.items()},
        body=body,
        agent_id=request.headers.get("x-agent-id"),
    )

    tool_names = _extract_tool_names(req)

    # Fail-closed: a malformed tool declaration we cannot verify must
    # reject the request outright (never silently forward upstream).
    malformed = _malformed_tool_declaration(req)
    if malformed:
        _tname, _tleth = _audit_tool_fields(req, tool_names)
        return await _deny_decision(
            req,
            reason=f"工具声明畸形，无法验证 — fail-closed 拒绝: {malformed}",
            status=400,
            matched_rule="malformed-tool-declaration",
            tool_name=_tname,
            tool_lethality=_tleth,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
        )

    # Reviewer REJECT fix: compare NORMALIZED names (NFKC + casefold) on
    # both sides. Raw exact-match here would let 'Delete_File' /
    # 'delete_fιle' (U+03B9) slip past the blacklist even though
    # _norm_tool_name exists. Keep the original name for the reason text.
    _dangerous_norms = {_norm_tool_name(n) for n in DANGEROUS_TOOL_NAMES}
    dangerous_tools = [
        t for t in tool_names if _norm_tool_name(t) in _dangerous_norms
    ]

    if dangerous_tools:
        _tname, _tleth = _audit_tool_fields(req, tool_names)
        return await _deny_decision(
            req,
            reason=f"LLM 请求声明危险工具调用 {dangerous_tools} — 拒绝转发",
            status=403,
            matched_rule="block-dangerous-tools",
            tool_name=_tname,
            tool_lethality=_tleth,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
        )
    else:
        # ordinary chat → consult policy engine (allow-chat rule)
        await asyncio.to_thread(policy_engine.maybe_reload)
        # v1.42.4-step2b: Ls 权重表热重载 (与 policy 同模式)
        await asyncio.to_thread(maybe_reload_lethality)
        rule = await asyncio.to_thread(
            policy_engine.evaluate, req.path, req.method, body, tenant_id
        )
        if rule is None:
            # same default semantics as /v1/intercept: no match → ALLOW
            verdict = Verdict.ALLOW
            reason = "无匹配策略，默认放行"
            status = 200
            matched_rule = None
        elif rule.action == "ALLOW":
            verdict = Verdict.ALLOW
            reason = f"匹配规则 '{rule.name}' → 放行"
            status = 200
            matched_rule = rule.name
        elif rule.action == "ALLOW_WITH_WARNING":
            # TASK-REAL-012 Phase 4 (治理大脑 Phase 1): 放行但附警告（可观测）
            verdict = Verdict.ALLOW_WITH_WARNING
            reason = rule.reason or f"匹配规则 '{rule.name}' → 放行但警告"
            status = 200
            matched_rule = rule.name
        elif rule.action == "SUSPEND":
            # 挂起审查 — 拒绝转发（语义区别于 DENY，供人工审查队列）
            verdict = Verdict.SUSPEND
            reason = rule.reason or f"匹配规则 '{rule.name}' → 挂起审查"
            status = 403
            matched_rule = rule.name
        else:
            verdict = Verdict.ESCALATE
            reason = f"匹配规则 '{rule.name}' → 升级"
            status = 202
            matched_rule = rule.name

    _tname, _tleth = _audit_tool_fields(req, tool_names)
    # TASK-REAL-012 Phase 4 (治理大脑 Phase 1): rationale 可解释字段
    _rationale = (f"rule={matched_rule}" if matched_rule else "no-rule(default-allow)")
    decision = DecisionRecord(
        id=str(uuid.uuid4()),
        verdict=verdict,
        reason=reason,
        matched_rule=matched_rule,
        path=req.path,
        method=req.method,
        agent_id=req.agent_id,
        tool_name=_tname,
        tool_lethality=_tleth,
        trace_id=trace_id,
        parent_span_id=parent_span_id,
        rationale=_rationale,
    )
    # v0.2.2 (external critique #3.1): sqlite3 writes are synchronous — run in
    # the thread pool so the event loop is not blocked (Storage has an internal
    # threading.Lock to serialize access to the shared connection).
    await asyncio.to_thread(storage.save, decision.model_dump(mode="json"))
    # v1.42.1-step2: CoT 决策轨迹回放 → decision_meta.cot (fail-soft)
    await _record_meta_soft(decision, method=req.method, path=req.path,
                            matched_rule=matched_rule, trace_id=trace_id,
                            reason=reason, tool_name=_tname,
                            tool_lethality=_tleth)
    _trace_headers = _signed_trace_headers(trace_id, decision.id)
    # v1.42.3-step4: 输出侧审计的 CoT 回调 (None = 观察层未接线, fail-soft)
    _on_semantic = (meta_observer.append_semantic
                    if meta_observer is not None else None)

    if verdict in (Verdict.DENY, Verdict.SUSPEND, Verdict.ESCALATE):
        return web.json_response(
            {
                "error": {
                    "message": reason,
                    "type": "governance_denied",
                    "decision_id": decision.id,
                }
            },
            status=status,
            headers=_trace_headers,
        )
    # ALLOW / ALLOW_WITH_WARNING 转发前附加治理警告头（可观测）
    if verdict == Verdict.ALLOW_WITH_WARNING:
        _trace_headers["X-Governance-Warning"] = reason

    # forward to upstream LLM (AGENT_BACKEND_URL + /v1/chat/completions)
    upstream = f"{AGENT_BACKEND_URL}/v1/chat/completions"
    stream = bool(body and body.get("stream"))
    sse = None
    try:
        async with ClientSession(timeout=ClientTimeout(total=10, connect=3)) as session:
            async with session.post(
                upstream,
                headers={
                    k: v for k, v in request.headers.items()
                    if k.lower() in FORWARD_HEADER_WHITELIST
                },
                json=body,
            ) as resp:
                if not stream:
                    # non-streaming: buffer the full JSON response (legacy path)
                    # DEBT-0018: 受控读取 — 超限截断, 避免超大响应撑爆内存;
                    # 截断后 JSON 解析失败 → 走 web.Response 透传截断文本。
                    _limit = _max_resp_bytes()
                    _raw = await resp.content.read(_limit + 1)
                    if len(_raw) > _limit:
                        _raw = _raw[:_limit]
                    text = _raw.decode("utf-8", errors="replace")
                    try:
                        # DEBT-0020: 输出侧异步补判 — fire-and-forget, 不阻塞返回
                        # v1.42.3-step4: 附带 decision_id + on_semantic → Judge
                        # 裁决以 semantic_judge 事件追加到该决策的 CoT 轨迹。
                        if semantic_hook_enabled():
                            asyncio.create_task(semantic_output_audit_async(
                                trace_id, text, base_reason="chat non-streaming",
                                decision_id=decision.id, on_semantic=_on_semantic))
                        return web.json_response(json.loads(text), status=resp.status,
                                                 headers=_trace_headers)
                    except json.JSONDecodeError:
                        if semantic_hook_enabled():
                            asyncio.create_task(semantic_output_audit_async(
                                trace_id, text, base_reason="chat non-streaming",
                                decision_id=decision.id, on_semantic=_on_semantic))
                        return web.Response(text=text, status=resp.status,
                                            headers=_trace_headers)
                # DEBT-0004: SSE streaming pass-through — forward upstream
                # text/event-stream chunk-by-chunk without buffering (TTFT
                # no longer waits for the full response; client gets chunks
                # as they arrive). Content-Type is forced so OpenAI SDK
                # clients parse the stream correctly.
                sse = web.StreamResponse(
                    status=resp.status,
                    headers={"Content-Type": "text/event-stream"},
                )
                await sse.prepare(request)
                # TASK-REAL-011.1 (Critic-Security): 流式转发分支同样回传
                # trace 头 — 客户端 (LangChain 回调) 可读取 X-Span-ID 关联
                # 本次决策的决策记录。
                sse.headers["X-Trace-ID"] = trace_id
                sse.headers["X-Span-ID"] = decision.id
                # DEBT-0020: 流式转发边转发边有界累积 (上限 AGENT_RESPONSE_MAX_CHARS,
                # 不破"流式不缓冲"原则 — 累积有界, TTFT 不受影响), 转发完成后
                # fire-and-forget 补判 agent_response。
                _out_buf = bytearray()
                async for chunk in resp.content.iter_chunked(1024):
                    await sse.write(chunk)
                    if len(_out_buf) < AGENT_RESPONSE_MAX_CHARS:
                        _out_buf += chunk[: AGENT_RESPONSE_MAX_CHARS - len(_out_buf)]
                await sse.write_eof()
                if semantic_hook_enabled() and _out_buf:
                    asyncio.create_task(semantic_output_audit_async(
                        trace_id,
                        _out_buf.decode("utf-8", errors="replace"),
                        base_reason="chat streaming",
                        decision_id=decision.id, on_semantic=_on_semantic,
                    ))
                return sse
    except Exception as e:
        logger.warning("chat forward failed: %s", e)
        logger.debug("chat forward traceback:\n%s", traceback.format_exc())
        if sse is None:
            return web.json_response(
                {"error": {"message": "upstream LLM unreachable", "type": "upstream_error"}},
                status=502,
            )
        # stream already started — propagate so aiohttp terminates the
        # connection; the client sees a truncated SSE stream (standard).
        raise


# ── app factory ─────────────────────────────────────────────────────

async def _flush_pending_on_shutdown(app: web.Application) -> None:
    """Flush degraded-mode pending records on clean shutdown (DEBT-0010).

    storage.save() buffers entries in memory while sqlite3 is unavailable
    (DEBT-0008 degraded mode). On shutdown we retry the flush once so the
    last decisions are not lost silently. Registered via on_cleanup so it
    runs on SIGINT/SIGTERM graceful shutdown, not only SIGKILL.

    NOTE (DEBT-0002 hardening, REAL-003): must be async — aiohttp signals
    await each receiver; a sync function returning None crashes cleanup
    with "object NoneType can't be used in 'await' expression".
    """
    if storage is None:
        return
    try:
        # DEBT-0015: independent timeout — the shutdown path must NEVER exceed
        # web.run_app(shutdown_timeout=10): a stuck DB would otherwise eat the
        # whole graceful-shutdown budget and block on_cleanup completion.
        n = await asyncio.wait_for(
            asyncio.to_thread(storage.flush_pending), timeout=SHUTDOWN_FLUSH_TIMEOUT
        )
        if n:
            logger.info("shutdown: flushed %d pending decision(s)", n)
    except asyncio.TimeoutError:
        logger.warning(
            "shutdown flush_pending exceeded %ds — records remain in fallback log (DEBT-0014/0015)",
            SHUTDOWN_FLUSH_TIMEOUT,
        )
    except Exception as e:  # noqa: BLE001 — shutdown path must never crash the app
        logger.warning("shutdown flush_pending failed: %s", e)
        logger.debug("shutdown flush_pending traceback:\n%s", traceback.format_exc())


def create_app(config_path: Optional[str] = None,
               auth_override: Optional[TenantAuth] = None,
               meta_observer_override: Optional[MetacognitionObserver] = None) -> web.Application:
    """Build the aiohttp app.

    config_path: policies YAML (默认 ./config/policies.yaml)。
    auth_override: P6 身份认证实例 (TenantAuth.from_yaml(...)); None 时若
    AUTH_ENABLED=1 自动加载 config/tenants.yaml; 否则认证关闭 (兼容模式)。
    meta_observer_override: v1.42.1-step2 元认知观察层注入 (测试可传
    :memory: 实例); None 时若 GOV_META_DB env 设置则自动接线, 否则不接线
    (opt-in, 与 SEMANTIC_HOOK_ENABLED 同模式)。
    """
    global policy_engine, storage, escalate_count_since_resolve, last_escalate_time, breaker_tripped_until, _escalate_lock
    # TASK-REAL-012 Phase 4 (治理大脑 Phase 1): config_path 可注入 —
    # 测试/多租户可加载独立策略文件；None 保持默认 config/policies.yaml。
    global auth  # P6: 认证门读取全局 auth; 显式注入优先, 否则 AUTH_ENABLED 自动加载
    global meta_observer  # v1.42.1-step2: 观察层全局接线点
    auth = load_auth_or_none() if auth_override is None else auth_override
    if auth is not None:
        logger.info("P6 auth enabled: %d tenant(s) — %s", len(auth.tenant_ids()),
                    ", ".join(auth.tenant_ids()))
    policy_engine = PolicyEngine(config_path)
    # P-AST: Priority 0 AST 硬阻断引擎注入 (Tree-sitter 裁决)。
    # fail-closed: ASTGuard 加载失败（查询文件缺失/损坏/语言包不可用）→ 拒绝启动,
    # 除非显式设置环境变量 AG_AST_DISABLE=1（逃生舱, 仅限无代码分析需求的部署）。
    if os.environ.get("AG_AST_DISABLE") != "1":
        try:
            from .ast_guard import ASTGuard
            ast_guard = ASTGuard()
            policy_engine.ast_guard = ast_guard
            logger.info("ASTGuard loaded: %s", ", ".join(ast_guard.loaded_languages))
        except Exception as e:  # noqa: BLE001 — fail-closed: AST 缺失必须拒绝启动
            logger.error("ASTGuard failed to load (fail-closed): %s", e)
            raise
    storage = Storage()
    # DEBT-0011: restore persisted breaker state (restart must not reset counters)
    breaker_state = storage.load_breaker_state()
    escalate_count_since_resolve = int(breaker_state.get("count", 0))
    last_escalate_time = float(breaker_state.get("last_escalate", 0.0))
    breaker_tripped_until = float(breaker_state.get("tripped_until", 0.0))
    _escalate_lock = asyncio.Lock()
    # v1.42.1-step2: 元认知观察层接线 — override 优先 (测试), 否则 GOV_META_DB
    # env opt-in; None = 不接线 (向后兼容, 现有测试零影响)。
    if meta_observer_override is not None:
        meta_observer = meta_observer_override
        logger.info("metacognition observer wired (override)")
    elif os.environ.get("GOV_META_DB"):
        meta_observer = MetacognitionObserver(db_path=os.environ["GOV_META_DB"])
        logger.info("metacognition observer wired: %s", os.environ["GOV_META_DB"])
    else:
        meta_observer = None

    app = web.Application()
    app.on_cleanup.append(_flush_pending_on_shutdown)
    app.router.add_post("/v1/intercept", intercept_handler)
    app.router.add_post("/v1/chat/completions", chat_completions_handler)
    app.router.add_get("/v1/health", health_handler)
    app.router.add_get("/metrics", metrics_handler)
    app.router.add_get("/v1/decisions", decisions_handler)
    # TASK-REAL-011 (C): trace 因果调用树查询端点
    app.router.add_get("/v1/trace/{trace_id}", trace_handler)
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app = create_app()
    logger.info("governance-gateway v0.4.0 starting on :9000")
    # DEBT-0007: explicit shutdown_timeout (default 60s) — fast graceful
    # shutdown lets on_cleanup flush pending decisions (DEBT-0010) quickly.
    web.run_app(app, port=9000, shutdown_timeout=10)
