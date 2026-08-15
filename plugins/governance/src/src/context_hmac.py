"""Context Hook HMAC — L3 治理大脑收尾（TASK-REAL-012 Phase 5）。

防止 Agent 篡改 X-Trace-ID / X-Parent-Span-ID / X-Span-ID 治理头伪造审计链，
确保因果追踪不可伪造。

启用方式: 设置环境变量 CONTEXT_HMAC_KEY（任意非空密钥）。
未设置 = 兼容模式（不验证、不签名，行为与 v0.5.0 完全一致）。

防伪语义（设计裁决）:
  - 验证失败 → 头值视为不可信 → 调用方 fail-safe 降级（新链根/忽略父 ID），
    伪造的因果链被隔离成孤立根节点 —— 拒绝而非报错，协作元数据不破坏可用性。
  - 防重放: 签名携带时间戳，超过 MAX_CLOCK_SKEW_S 窗口的旧签名失效。
  - canonical 串固定字段顺序 + 小写头名，杜绝签名歧义。
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Dict, Optional, Tuple

# 参与签名的治理头（标准头名，取值按此顺序拼 canonical）
TRACE_HEADER = "X-Trace-ID"
PARENT_HEADER = "X-Parent-Span-ID"
SPAN_HEADER = "X-Span-ID"
GOV_VERSION_HEADER = "X-Governance-Version"

SIGNATURE_HEADER = "X-Governance-Signature"
TIMESTAMP_HEADER = "X-Governance-Timestamp"

MAX_CLOCK_SKEW_S = 300  # ±5min 防重放时间窗

_ENV_KEY = "CONTEXT_HMAC_KEY"


def _secret() -> Optional[str]:
    val = os.environ.get(_ENV_KEY)
    return val if val else None


def enabled() -> bool:
    """HMAC 是否启用（CONTEXT_HMAC_KEY 非空）。"""
    return _secret() is not None


def _canonical(headers: Dict[str, str]) -> str:
    """规范串: 固定顺序 + 小写头名 + 值，缺失头以空串占位（防删除重签）。"""
    parts = []
    for name in (TRACE_HEADER, PARENT_HEADER, SPAN_HEADER, GOV_VERSION_HEADER):
        parts.append(f"{name.lower()}={headers.get(name, '')}")
    return "\n".join(parts)


def sign_headers(headers: Dict[str, str], secret: Optional[str] = None,
                 ts: Optional[int] = None) -> Dict[str, str]:
    """对治理头计算 HMAC-SHA256 签名，返回新增的签名/时间戳头。

    未启用（无密钥）时返回空 dict —— 保持响应头与兼容模式一致。
    """
    secret = secret or _secret()
    if secret is None:
        return {}
    ts = ts if ts is not None else int(time.time())
    msg = f"{_canonical(headers)}\nts={ts}"
    sig = hmac.new(secret.encode("utf-8"), msg.encode("utf-8"),
                   hashlib.sha256).hexdigest()
    return {SIGNATURE_HEADER: sig, TIMESTAMP_HEADER: str(ts)}


def verify_headers(headers: Dict[str, str], secret: Optional[str] = None,
                   now: Optional[int] = None) -> bool:
    """验证签名 + 时间窗。任一条件不满足 → False（调用方 fail-safe 降级）。

    - 无密钥（未启用）: 返回 True（兼容模式——无事可验即信任，见 validate_trace）
    - 签名缺失/时间戳缺失/格式错/超窗/不匹配: False
    """
    secret = secret or _secret()
    if secret is None:
        return True
    sig = headers.get(SIGNATURE_HEADER, "")
    ts_s = headers.get(TIMESTAMP_HEADER, "")
    if not sig or not ts_s:
        return False
    try:
        ts = int(ts_s)
    except (TypeError, ValueError):
        return False
    now = now if now is not None else int(time.time())
    if abs(now - ts) > MAX_CLOCK_SKEW_S:
        return False
    msg = f"{_canonical(headers)}\nts={ts}"
    expected = hmac.new(secret.encode("utf-8"), msg.encode("utf-8"),
                        hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def validate_trace_headers(headers: Dict[str, str]) -> Optional[Tuple[str, str]]:
    """入口钩子（供 _trace_context 调用）: 返回 (trace_id, parent_span_id) 或 None。

    - 未启用（兼容模式）: 返回 None —— 调用方按 v0.5.0 逻辑提取（现状不变）
    - 启用且验证通过: 返回头内声明的 trace 上下文（可信，调用方做长度 fail-safe）
    - 启用且验证失败/缺失签名: 返回 ("", "") 空标记 —— 调用方必须降级
      （生成新链根 + 忽略父 ID），伪造头永不进入审计链
    """
    if not enabled():
        return None
    if verify_headers(headers):
        trace_id = headers.get(TRACE_HEADER, "")
        parent_span_id = headers.get(PARENT_HEADER, "")
        return (trace_id, parent_span_id)
    return ("", "")
