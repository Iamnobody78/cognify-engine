"""P1 (暗雷区) — 语义钩子异步弱监督 + 撤销注册表测试。

核心语义:
  1. 主链路不再 await judge（消除启用时 +150ms 阻塞）—— 响应即时返回
  2. 后台审计高风险 → revoke trace → 后续请求短路 SUSPEND（403，可审计）
  3. 只升不降保持: 静态 DENY 是最终裁决；judge 被攻破最坏 = 多撤一条链
"""

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path

import aiohttp.web as aio_web
import pytest
import yaml
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from src import semantic_hook
from src.main import create_app
from src.revoke import RevokeRegistry


# ── 1/3. RevokeRegistry 单元 ───────────────────────────────────────────

def test_revoke_and_query():
    reg = RevokeRegistry()
    reg.revoke("trace-1", "高风险", 0.99)
    assert reg.is_revoked("trace-1") is True
    assert reg.is_revoked("trace-2") is False
    assert reg.reason_for("trace-1") == "高风险"
    assert reg.score_for("trace-1") == 0.99


def test_revoke_idempotent_overwrites_reason():
    reg = RevokeRegistry()
    reg.revoke("t", "原因A", 0.9)
    reg.revoke("t", "原因B", 0.95)
    assert reg.reason_for("t") == "原因B"
    assert reg.score_for("t") == 0.95


def test_revoke_empty_trace_ignored():
    reg = RevokeRegistry()
    reg.revoke("", "x", 1.0)
    reg.revoke(None, "x", 1.0)  # type: ignore[arg-type]
    assert len(reg) == 0


def test_capacity_evicts_oldest():
    reg = RevokeRegistry(max_entries=3)
    reg.revoke("a", "1", 0.1)
    reg.revoke("b", "2", 0.2)
    reg.revoke("c", "3", 0.3)
    reg.revoke("d", "4", 0.4)  # 超出 → 驱逐最旧 "a"
    assert reg.is_revoked("a") is False
    assert reg.is_revoked("b") is True
    assert reg.is_revoked("d") is True


def test_clear():
    reg = RevokeRegistry()
    reg.revoke("t", "x", 1.0)
    reg.clear()
    assert len(reg) == 0


# ── 2/3. semantic_audit_async 单元（真实 judge server）─────────────────

async def _judge_server(score, delay=0.0):
    """临时 judge: 返回固定 score，可选延迟。返回 (runner, base_url)。"""
    app = aio_web.Application()

    async def _handler(request):
        if delay:
            await asyncio.sleep(delay)
        return aio_web.json_response({"score": score, "flags": ["deceptive-rewrite"]})

    app.router.add_post("/v1/judge", _handler)
    runner = aio_web.AppRunner(app)
    await runner.setup()
    site = aio_web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return runner, f"http://127.0.0.1:{port}/v1/judge"


@pytest.mark.asyncio
async def test_audit_high_score_revokes():
    """高风险 judge → 撤销 trace（副作用落到进程级单例注册表）。"""
    runner, url = await _judge_server(score=0.99)
    try:
        old_enabled = semantic_hook.SEMANTIC_HOOK_ENABLED
        old_url = semantic_hook.SEMANTIC_JUDGE_URL
        semantic_hook.SEMANTIC_HOOK_ENABLED = True
        semantic_hook.SEMANTIC_JUDGE_URL = url
        from src import revoke as revoke_mod
        old_singleton = revoke_mod.revoke_registry
        revoke_mod.revoke_registry = RevokeRegistry()  # 隔离: 只断言本次副作用
        try:
            result = await semantic_hook.semantic_audit_async(
                "chain-9", "我要删除数据库", base_reason="rule-test")
            assert result["override"] == "ESCALATE"
            assert revoke_mod.revoke_registry.is_revoked("chain-9") is True
            assert "语义审计撤销" in revoke_mod.revoke_registry.reason_for("chain-9")
        finally:
            revoke_mod.revoke_registry = old_singleton
            semantic_hook.SEMANTIC_HOOK_ENABLED = old_enabled
            semantic_hook.SEMANTIC_JUDGE_URL = old_url
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_audit_low_score_no_revoke():
    runner, url = await _judge_server(score=0.3)
    try:
        old_enabled = semantic_hook.SEMANTIC_HOOK_ENABLED
        old_url = semantic_hook.SEMANTIC_JUDGE_URL
        semantic_hook.SEMANTIC_HOOK_ENABLED = True
        semantic_hook.SEMANTIC_JUDGE_URL = url
        from src import revoke as revoke_mod
        old_singleton = revoke_mod.revoke_registry
        revoke_mod.revoke_registry = RevokeRegistry()
        try:
            result = await semantic_hook.semantic_audit_async("chain-low", "正常请求")
            assert result["override"] is None
            assert revoke_mod.revoke_registry.is_revoked("chain-low") is False
        finally:
            revoke_mod.revoke_registry = old_singleton
            semantic_hook.SEMANTIC_HOOK_ENABLED = old_enabled
            semantic_hook.SEMANTIC_JUDGE_URL = old_url
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_audit_disabled_noop():
    old_enabled = semantic_hook.SEMANTIC_HOOK_ENABLED
    semantic_hook.SEMANTIC_HOOK_ENABLED = False
    try:
        assert await semantic_hook.semantic_audit_async("t", "p") is None
    finally:
        semantic_hook.SEMANTIC_HOOK_ENABLED = old_enabled


# ── 3/3. 集成: 异步弱监督 + 撤销短路 HTTP ──────────────────────────────

def _write_empty_policy(tmpdir):
    pf = Path(tmpdir) / "p1.yaml"
    pf.write_text(yaml.safe_dump({"name": "p1", "rules": []}), encoding="utf-8")
    return str(pf)


class TestSemanticAsyncIntegration(AioHTTPTestCase):
    """真实 HTTP: 请求即时放行 → 后台审计撤销 → 同 trace 后续请求 SUSPEND 403。"""

    async def setUpAsync(self):
        self._old_enabled = semantic_hook.SEMANTIC_HOOK_ENABLED
        self._old_url = semantic_hook.SEMANTIC_JUDGE_URL
        self._old_timeout = semantic_hook.SEMANTIC_HOOK_TIMEOUT
        semantic_hook.SEMANTIC_HOOK_ENABLED = True
        # AioHTTPTestCase + pytest 的 loop 混杂会使 judge 响应跨 loop 延迟,
        # 放大测试环境超时(生产默认 0.15s 收紧保持不变)。
        semantic_hook.SEMANTIC_HOOK_TIMEOUT = 2.0
        self._judge_runner, self._judge_url = await _judge_server(score=0.99)
        semantic_hook.SEMANTIC_JUDGE_URL = self._judge_url
        await super().setUpAsync()

    async def tearDownAsync(self):
        await super().tearDownAsync()
        await self._judge_runner.cleanup()
        semantic_hook.SEMANTIC_HOOK_ENABLED = self._old_enabled
        semantic_hook.SEMANTIC_JUDGE_URL = self._old_url
        semantic_hook.SEMANTIC_HOOK_TIMEOUT = self._old_timeout
        from src.revoke import revoke_registry
        revoke_registry.clear()

    async def get_application(self):
        self._tmpdir = Path(tempfile.mkdtemp(prefix="p1-"))
        self.addCleanup(shutil.rmtree, self._tmpdir, ignore_errors=True)
        return create_app(_write_empty_policy(self._tmpdir))

    @unittest_run_loop
    async def test_first_request_passes_then_trace_revoked(self):
        # 第一个请求: 静态 ALLOW（不等待 judge）
        r1 = await self.client.post(
            "/v1/intercept",
            headers={"X-Trace-ID": "chain-1"},
            json={"path": "/api/ok", "method": "GET", "body": {}})
        assert r1.status == 200

        # 后台审计完成（等待 judge 结果落地到撤销注册表）
        await asyncio.sleep(0.3)
        from src.revoke import revoke_registry
        assert revoke_registry.is_revoked("chain-1") is True

        # 同 trace 后续请求 → 短路 SUSPEND 403（可审计）
        r2 = await self.client.post(
            "/v1/intercept",
            headers={"X-Trace-ID": "chain-1"},
            json={"path": "/api/ok", "method": "GET", "body": {}})
        assert r2.status == 403
        data = await r2.json()
        assert data["verdict"] == "SUSPEND"
        assert "语义审计撤销" in data.get("reason", "")

    @unittest_run_loop
    async def test_dynamic_verdict_overrides_deny(self):
        """静态 DENY 优先: 即使 trace 被撤销，DENY 规则仍是最终裁决。"""
        # 用一个自定义策略: DENY /api/forbidden
        pf = Path(self._tmpdir) / "p1.yaml"
        pf.write_text(yaml.safe_dump({"name": "p1", "rules": [
            {"name": "block-forbidden", "path_pattern": "/api/forbidden",
             "method": "POST", "action": "DENY", "reason": "禁止"},
        ]}), encoding="utf-8")
        await asyncio.sleep(0.3)  # 让后台撤销完成
        from src.revoke import revoke_registry
        revoke_registry.revoke("deny-chain", "撤销测试", 1.0)
        resp = await self.client.post(
            "/v1/intercept",
            headers={"X-Trace-ID": "deny-chain"},
            json={"path": "/api/forbidden", "method": "POST", "body": {}})
        assert resp.status == 403
        data = await resp.json()
        assert data["verdict"] == "DENY"  # 撤销不覆盖 DENY（只升不降保持）
