"""P6 (外部评审缺口 #1): 身份认证 + 多租户隔离 — 验收测试。

验收标准 (用户协议):
  - 身份缺失 → 401; 无效 Key → 401
  - 跨租户访问 (X-Tenant-ID 与认证身份不符) → 403
  - 租户私有规则隔离: tenant-a 规则不作用于 tenant-b 请求
  - 兼容模式 (auth 未启用) 行为与 v1.13.0 完全一致 (零回归)
  - 复用 Phase 5 HMAC: 伪造治理签名头 → 401 (服务身份边界)
"""

import hashlib
import os
import tempfile
import unittest
from pathlib import Path

import yaml
from aiohttp.test_utils import AioHTTPTestCase, TestClient

from src import main
from src.auth import TenantAuth
from src.policy import PolicyEngine, Rule, _parse_json_path

A_TENANT = "tenant-a"
B_TENANT = "tenant-b"
KEY_A = "test-key-a-0001"
KEY_B = "test-key-b-0001"
POLICIES = Path(__file__).parent / ".." / "config" / "policies.yaml"


def _auth(data=None):
    return TenantAuth.from_dict(data or {
        "tenants": [
            {"id": A_TENANT, "api_keys": [KEY_A]},
            {"id": B_TENANT, "api_keys": [KEY_B]},
        ]
    })


def _make_request(headers):
    """构造最小 request stub (headers 足以覆盖 resolve_tenant 路径)。"""
    from types import SimpleNamespace
    return SimpleNamespace(headers=headers)


# ── 1. TenantAuth 单元 ───────────────────────────────────────────────
class TestTenantAuth(unittest.TestCase):
    def test_authenticate_maps_key_to_tenant(self):
        a = _auth()
        assert a.authenticate(KEY_A) == A_TENANT
        assert a.authenticate(KEY_B) == B_TENANT

    def test_authenticate_invalid_key_returns_none(self):
        a = _auth()
        assert a.authenticate("wrong-key-9999") is None
        assert a.authenticate(None) is None

    def test_from_yaml_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "tenants.yaml"
            p.write_text(yaml.safe_dump({
                "tenants": [{"id": A_TENANT, "api_keys": [KEY_A]},
                            {"id": B_TENANT, "api_keys": [KEY_B]}],
            }, allow_unicode=True), encoding="utf-8")
            a = TenantAuth.from_yaml(str(p))
        assert a.authenticate(KEY_A) == A_TENANT
        assert a.tenant_ids() == [A_TENANT, B_TENANT]

    def test_short_key_rejected_fail_closed(self):
        with self.assertRaises(ValueError):
            TenantAuth.from_dict({"tenants": [{"id": "t", "api_keys": ["short"]}]})

    def test_duplicate_key_across_tenants_rejected(self):
        with self.assertRaises(ValueError):
            TenantAuth.from_dict({"tenants": [
                {"id": "t1", "api_keys": ["same-key-0001"]},
                {"id": "t2", "api_keys": ["same-key-0001"]},
            ]})

    def test_empty_tenants_rejected(self):
        with self.assertRaises(ValueError):
            TenantAuth.from_dict({"tenants": []})

    def test_duplicate_tenant_id_rejected(self):
        with self.assertRaises(ValueError):
            TenantAuth.from_dict({"tenants": [
                {"id": "t1", "api_keys": ["key-aaaa-0001"]},
                {"id": "t1", "api_keys": ["key-bbbb-0001"]},
            ]})


# ── 2. resolve_tenant 请求级 (401/403) ──────────────────────────────
class TestResolveTenant(unittest.TestCase):
    def setUp(self):
        self.a = _auth()

    def test_valid_key_without_declared_tenant_passes(self):
        tid, err = self.a.resolve_tenant(_make_request({
            "Authorization": f"Bearer {KEY_A}"}))
        assert err is None and tid == A_TENANT

    def test_valid_key_with_matching_tenant_passes(self):
        tid, err = self.a.resolve_tenant(_make_request({
            "Authorization": f"Bearer {KEY_A}",
            "X-Tenant-ID": A_TENANT}))
        assert err is None and tid == A_TENANT

    def test_tenant_mismatch_returns_403(self):
        # 跨租户冒称: tenant-a 的 key 声明自己是 tenant-b → 403
        tid, err = self.a.resolve_tenant(_make_request({
            "Authorization": f"Bearer {KEY_A}",
            "X-Tenant-ID": B_TENANT}))
        assert tid is None
        assert err["status"] == 403 and err["error"] == "tenant_mismatch"

    def test_missing_key_returns_401(self):
        tid, err = self.a.resolve_tenant(_make_request({}))
        assert tid is None
        assert err["status"] == 401 and err["error"] == "unauthorized"

    def test_invalid_key_returns_401(self):
        tid, err = self.a.resolve_tenant(_make_request({
            "Authorization": "Bearer nope-999999"}))
        assert tid is None and err["status"] == 401

    def test_x_api_key_header_alternative(self):
        tid, err = self.a.resolve_tenant(_make_request({"X-API-Key": KEY_B}))
        assert err is None and tid == B_TENANT


# ── 3. 租户规则隔离 (engine 级) ─────────────────────────────────────
class TestTenantRuleIsolation(unittest.TestCase):
    def _write(self, tmp_path):
        p = Path(tmp_path) / "policies.yaml"
        p.write_text(yaml.safe_dump({
            "name": "tenant-isolation", "version": "0.0.0",
            "rules": [
                {"name": "global-deny", "path_pattern": "/api/shared",
                 "method": "POST", "action": "DENY", "priority": 10},
                {"name": "a-private", "path_pattern": "/api/private",
                 "method": "POST", "action": "DENY", "priority": 20,
                 "tenant_id": A_TENANT},
                {"name": "b-private", "path_pattern": "/api/private",
                 "method": "POST", "action": "DENY", "priority": 20,
                 "tenant_id": B_TENANT},
            ],
        }, allow_unicode=True), encoding="utf-8")
        return PolicyEngine(str(p))

    def test_private_rule_only_affects_own_tenant(self):
        with tempfile.TemporaryDirectory() as td:
            eng = self._write(td)
            r_a = eng.evaluate("/api/private", "POST", None, tenant_id=A_TENANT)
            r_b = eng.evaluate("/api/private", "POST", None, tenant_id=B_TENANT)
            r_none = eng.evaluate("/api/private", "POST", None, tenant_id=None)
            assert r_a.name == "a-private"      # tenant-a 命中自己的私有规则
            assert r_b.name == "b-private"      # tenant-b 命中自己的私有规则
            assert r_none is None               # 未认证: 私有规则全部跳过

    def test_cross_tenant_cannot_see_other_private_rule(self):
        # tenant-a 请求 /api/private 绝不命中 b-private → 403 语义由规则隔离保证
        with tempfile.TemporaryDirectory() as td:
            eng = self._write(td)
            r = eng.evaluate("/api/private", "POST", None, tenant_id=A_TENANT)
            assert r.name != "b-private"

    def test_global_rule_applies_to_all_tenants(self):
        with tempfile.TemporaryDirectory() as td:
            eng = self._write(td)
            assert eng.evaluate("/api/shared", "POST", None, tenant_id=A_TENANT).name == "global-deny"
            assert eng.evaluate("/api/shared", "POST", None, tenant_id=B_TENANT).name == "global-deny"
            assert eng.evaluate("/api/shared", "POST", None, tenant_id=None).name == "global-deny"

    def test_rule_tenant_field_validation(self):
        with self.assertRaises(ValueError):
            Rule(name="bad", path_pattern="*", method="POST", action="DENY",
                 priority=1, tenant_id="  ")  # 空串 → fail-closed 拒绝载入
        with self.assertRaises(ValueError):
            Rule(name="bad2", path_pattern="*", method="POST", action="DENY",
                 priority=1, tenant_id=42)    # 非字符串 → fail-closed


# ── 4. aiohttp 集成 (真实请求) ──────────────────────────────────────
class TestAuthIntegration(AioHTTPTestCase):
    async def get_application(self):
        return main.create_app(str(POLICIES))

    async def test_compat_mode_no_key_still_works(self):
        # 兼容模式 (auth 未注入, AUTH_ENABLED 未设): v1.13.0 行为不变
        resp = await self.client.post("/v1/intercept", json={
            "path": "/api/safe", "method": "GET", "body": None,
        })
        assert resp.status in (200, 202), resp.status  # 无 401 即兼容
        body = await resp.json()
        assert "verdict" in body or "decision" in body or "status" in body


class TestAuthEnabled(AioHTTPTestCase):
    async def get_application(self):
        return main.create_app(str(POLICIES),
                               auth_override=_auth())

    async def test_missing_key_401(self):
        resp = await self.client.post("/v1/intercept", json={
            "path": "/api/safe", "method": "GET", "body": None,
        })
        assert resp.status == 401
        body = await resp.json()
        assert body["error"] == "unauthorized"

    async def test_invalid_key_401(self):
        resp = await self.client.post("/v1/intercept", json={
            "path": "/api/safe", "method": "GET", "body": None,
        }, headers={"Authorization": "Bearer bad-key-0000"})
        assert resp.status == 401

    async def test_valid_key_passes(self):
        resp = await self.client.post("/v1/intercept", json={
            "path": "/api/safe", "method": "GET", "body": None,
        }, headers={"Authorization": f"Bearer {KEY_A}"})
        assert resp.status in (200, 202, 403), resp.status

    async def test_cross_tenant_declaration_403(self):
        # tenant-a 的 key 声明 X-Tenant-ID: tenant-b → 跨租户 → 403
        resp = await self.client.post("/v1/intercept", json={
            "path": "/api/safe", "method": "GET", "body": None,
        }, headers={"Authorization": f"Bearer {KEY_A}",
                    "X-Tenant-ID": B_TENANT})
        assert resp.status == 403
        body = await resp.json()
        assert body["error"] == "tenant_mismatch"

    async def test_health_probe_unprotected(self):
        # 存活探针不受身份门保护 (基础设施探针无凭证)
        resp = await self.client.get("/v1/health")
        assert resp.status in (200, 404), resp.status

    async def test_decisions_endpoint_protected(self):
        resp = await self.client.get("/v1/decisions")
        assert resp.status == 401
        resp2 = await self.client.get(
            "/v1/decisions",
            headers={"X-API-Key": KEY_B})
        assert resp2.status in (200, 404, 401), resp2.status

    async def test_trace_endpoint_protected(self):
        resp = await self.client.get("/v1/trace/whatever")
        assert resp.status == 401

    async def test_chat_endpoint_protected(self):
        resp = await self.client.post("/v1/chat/completions", json={
            "messages": [{"role": "user", "content": "hi"}],
        })
        assert resp.status == 401

    async def test_same_tenant_declaration_passes(self):
        resp = await self.client.post("/v1/intercept", json={
            "path": "/api/safe", "method": "GET", "body": None,
        }, headers={"Authorization": f"Bearer {KEY_B}",
                    "X-Tenant-ID": B_TENANT})
        assert resp.status in (200, 202, 403), resp.status


# ── 5. HMAC 服务签名复用 (Phase 5 原语) ─────────────────────────────
class TestServiceSignature(unittest.TestCase):
    def setUp(self):
        self._old_key = os.environ.get("CONTEXT_HMAC_KEY")
        os.environ["CONTEXT_HMAC_KEY"] = "test-hmac-key-p6"

    def tearDown(self):
        if self._old_key is None:
            os.environ.pop("CONTEXT_HMAC_KEY", None)
        else:
            os.environ["CONTEXT_HMAC_KEY"] = self._old_key

    def test_forged_signature_rejected_401(self):
        # 伪造治理签名头: 服务身份边界拒绝 (比链根隔离更严, 信任边界不同)
        err = TenantAuth.verify_service_signature(_make_request({
            "X-Trace-ID": "t-123",
            "X-Governance-Signature": "deadbeef" * 8,
        }))
        assert err is not None and err["status"] == 401
        assert err["error"] == "forged_signature"

    def test_no_signature_headers_pass(self):
        err = TenantAuth.verify_service_signature(_make_request({}))
        assert err is None  # 无治理头 = 无需签名校验


if __name__ == "__main__":
    unittest.main()
