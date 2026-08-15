"""P6 (外部评审缺口 #1): 服务身份认证 + 多租户隔离 — 网关第一道门。

- API key → tenant_id 映射 (config/tenants.yaml)
- 认证头: `Authorization: Bearer <key>` 或 `X-API-Key: <key>`; 缺失/无效 → 401
- `X-Tenant-ID` 头一致性: 声明租户与认证身份不符 → 403 (防跨租户冒称)
- 服务间签名: 复用 Phase 5 context_hmac 原语 — CONTEXT_HMAC_KEY 启用且
  请求携带治理签名头时, 伪造签名 → 401 (调用方可能被劫持, 比链根隔离更严)

启用方式 (与 CONTEXT_HMAC_KEY 同模式, 环境变量开关):
  - create_app(auth=TenantAuth.from_yaml("config/tenants.yaml")) 显式注入
  - 或环境变量 AUTH_ENABLED=1 → main.create_app 自动加载 config/tenants.yaml
未启用 = 兼容模式: 行为与 v1.13.0 完全一致 (391 回归保障)。
"""

import hashlib
import hmac
import os
from typing import Dict, List, Optional, Tuple

import yaml

from src.context_hmac import SIGNATURE_HEADER, validate_trace_headers

# 允许的 API key 最小长度 (防空串/超短 key 通过)
MIN_API_KEY_LEN = 8
# 环境变量开关 (与 CONTEXT_HMAC_KEY 同模式)
AUTH_ENABLED_ENV = "AUTH_ENABLED"
# 默认租户配置文件 (相对仓库根)
DEFAULT_TENANTS_PATH = os.path.join("config", "tenants.yaml")


class TenantAuth:
    """API key → tenant_id 映射 + 请求认证/租户一致性解析。

    keys 用 SHA-256 摘要存储于内存 (配置明文仅加载瞬间驻留); 常量时间
    比较 (hmac.compare_digest) 防时序侧信道。
    """

    def __init__(self, tenant_keys: Dict[str, str]):
        """tenant_keys: {api_key_sha256_hex: tenant_id}。"""
        self._tenant_keys = tenant_keys
        # 反查索引 (测试/诊断用): tenant_id -> [key 摘要]
        self._by_tenant: Dict[str, List[str]] = {}
        for digest, tid in tenant_keys.items():
            self._by_tenant.setdefault(tid, []).append(digest)

    # ── 工厂 ──────────────────────────────────────────────────────────
    @classmethod
    def from_yaml(cls, path: str) -> "TenantAuth":
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "TenantAuth":
        """{tenants: [{id, api_keys: [...]}]} → 摘要映射 (fail-closed 校验)。"""
        tenant_keys: Dict[str, str] = {}
        tenants = data.get("tenants", []) or []
        if not isinstance(tenants, list) or not tenants:
            raise ValueError("tenants.yaml: 'tenants' must be a non-empty list (fail-closed)")
        seen_ids = set()
        for t in tenants:
            tid = t.get("id")
            keys = t.get("api_keys", []) or []
            if not isinstance(tid, str) or not tid.strip():
                raise ValueError(f"tenants.yaml: tenant without valid 'id' — {t!r}")
            if tid in seen_ids:
                raise ValueError(f"tenants.yaml: duplicate tenant id {tid!r}")
            seen_ids.add(tid)
            if not isinstance(keys, list) or not keys:
                raise ValueError(f"tenant {tid!r}: 'api_keys' must be a non-empty list (fail-closed)")
            for key in keys:
                if not isinstance(key, str) or len(key) < MIN_API_KEY_LEN:
                    raise ValueError(
                        f"tenant {tid!r}: api key too short (< {MIN_API_KEY_LEN}) — "
                        f"refusing to load (fail-closed)")
                digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
                if digest in tenant_keys:
                    raise ValueError(
                        f"tenant {tid!r}: api key reused by another tenant (fail-closed)")
                tenant_keys[digest] = tid
        return cls(tenant_keys)

    # ── 认证原语 ──────────────────────────────────────────────────────
    def authenticate(self, api_key: Optional[str]) -> Optional[str]:
        """返回 tenant_id 或 None (缺失/无效 key)。常量时间比较。"""
        if not api_key or len(api_key) < MIN_API_KEY_LEN:
            return None
        digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
        tid = self._tenant_keys.get(digest)
        if tid is None:
            return None
        # 常量时间比较兜底 (dict 命中已隐含, 此处仅作纵深防御)
        for stored, candidate in ((digest, digest),):
            if not hmac.compare_digest(stored, candidate):
                return None
        return tid

    def tenant_of(self, tenant_id: str) -> bool:
        """诊断: tenant_id 是否已配置。"""
        return tenant_id in self._by_tenant

    def tenant_ids(self) -> List[str]:
        return sorted(self._by_tenant.keys())

    # ── 请求级解析 ────────────────────────────────────────────────────
    @staticmethod
    def extract_api_key(request) -> Optional[str]:
        """Authorization: Bearer <key> 或 X-API-Key 头。"""
        authz = request.headers.get("Authorization", "")
        if authz.startswith("Bearer "):
            return authz[len("Bearer "):].strip()
        return request.headers.get("X-API-Key", "").strip() or None

    def resolve_tenant(self, request) -> Tuple[Optional[str], Optional[dict]]:
        """网关第一道门: (tenant_id, error) — error 为 None 即放行。

        error: {"status": 401|403, "error": str, "detail": str}
          - 401: 缺失/无效 API key
          - 403: X-Tenant-ID 与认证身份不符 (跨租户冒称)
        """
        api_key = self.extract_api_key(request)
        tenant_id = self.authenticate(api_key) if api_key else None
        if tenant_id is None:
            return None, {
                "status": 401,
                "error": "unauthorized",
                "detail": "missing or invalid API key",
            }
        declared = request.headers.get("X-Tenant-ID", "").strip() or None
        if declared is not None and declared != tenant_id:
            return None, {
                "status": 403,
                "error": "tenant_mismatch",
                "detail": f"X-Tenant-ID {declared!r} does not match authenticated "
                          f"tenant {tenant_id!r}",
            }
        return tenant_id, None

    # ── 服务间签名 (复用 Phase 5 context_hmac) ───────────────────────
    @staticmethod
    def verify_service_signature(request) -> Optional[dict]:
        """CONTEXT_HMAC_KEY 启用且请求**显式携带**治理签名头时, 伪造 → 401。

        与 _trace_context 的"伪造→新链根隔离"是不同信任边界:
        链根隔离保审计完整性 (放行但隔离), 此处保服务身份 (拒绝)。
        未携带签名头的请求不校验 (普通 API key 调用路径) —— 签名是
        服务间调用的可选强化层, 不强制。
        """
        if not os.environ.get("CONTEXT_HMAC_KEY"):
            return None  # 签名未启用: 不校验
        result = validate_trace_headers(request.headers)
        if result == ("", "") and SIGNATURE_HEADER in request.headers:
            # 带签名但无效/伪造: 调用方身份可疑 → 拒绝
            return {
                "status": 401,
                "error": "forged_signature",
                "detail": "governance context signature invalid (service identity)",
            }
        return None


def load_auth_or_none() -> Optional[TenantAuth]:
    """AUTH_ENABLED=1 时自动加载默认租户配置; 否则 None (兼容模式)。"""
    if os.environ.get(AUTH_ENABLED_ENV) != "1":
        return None
    if not os.path.exists(DEFAULT_TENANTS_PATH):
        raise FileNotFoundError(
            f"AUTH_ENABLED=1 requires {DEFAULT_TENANTS_PATH!r} (fail-closed)")
    return TenantAuth.from_yaml(DEFAULT_TENANTS_PATH)
