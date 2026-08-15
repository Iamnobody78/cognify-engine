"""TASK-REAL-012 Phase 5 — Context Hook HMAC 测试。

单元层（src/context_hmac.py 纯函数）+ 集成层（main.py 入口信任门 + 响应签名）。
防伪语义: 伪造 trace 头 → 降级为新链根（隔离孤立节点），绝不进入审计链。
"""

import os
import shutil
import tempfile
import time
from pathlib import Path

import pytest
import yaml
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from src import context_hmac
from src.main import create_app

_SECRET = "phase5-test-secret"


def _write_empty_policy(tmpdir):
    pf = Path(tmpdir) / "hmac.yaml"
    pf.write_text(
        yaml.safe_dump({"name": "hmac", "version": "0.1", "rules": []}),
        encoding="utf-8")
    return str(pf)


# ── 1/2. 单元层 ───────────────────────────────────────────────────────

def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("CONTEXT_HMAC_KEY", raising=False)
    assert context_hmac.enabled() is False


def test_enabled_with_key(monkeypatch):
    monkeypatch.setenv("CONTEXT_HMAC_KEY", _SECRET)
    assert context_hmac.enabled() is True


def test_sign_verify_roundtrip(monkeypatch):
    monkeypatch.setenv("CONTEXT_HMAC_KEY", _SECRET)
    hdrs = {"X-Trace-ID": "abc-123", "X-Parent-Span-ID": "parent-9"}
    signed = context_hmac.sign_headers(hdrs)
    assert context_hmac.verify_headers({**hdrs, **signed}) is True


def test_verify_without_secret_trusts(monkeypatch):
    monkeypatch.delenv("CONTEXT_HMAC_KEY", raising=False)
    # 兼容模式: 无事可验即信任（调用方按 v0.5.0 逻辑提取）
    assert context_hmac.verify_headers({"X-Trace-ID": "x"}) is True


def test_tampered_trace_id_rejected(monkeypatch):
    monkeypatch.setenv("CONTEXT_HMAC_KEY", _SECRET)
    hdrs = {"X-Trace-ID": "abc-123", "X-Parent-Span-ID": "parent-9"}
    signed = context_hmac.sign_headers(hdrs)
    forged = {**hdrs, **signed, "X-Trace-ID": "evil-999"}
    assert context_hmac.verify_headers(forged) is False


def test_tampered_parent_span_rejected(monkeypatch):
    monkeypatch.setenv("CONTEXT_HMAC_KEY", _SECRET)
    hdrs = {"X-Trace-ID": "abc-123", "X-Parent-Span-ID": "parent-9"}
    signed = context_hmac.sign_headers(hdrs)
    forged = {**hdrs, **signed, "X-Parent-Span-ID": "evil-parent"}
    assert context_hmac.verify_headers(forged) is False


def test_missing_signature_rejected(monkeypatch):
    monkeypatch.setenv("CONTEXT_HMAC_KEY", _SECRET)
    assert context_hmac.verify_headers({"X-Trace-ID": "abc"}) is False


def test_expired_timestamp_rejected(monkeypatch):
    monkeypatch.setenv("CONTEXT_HMAC_KEY", _SECRET)
    hdrs = {"X-Trace-ID": "abc-123"}
    old_ts = int(time.time()) - context_hmac.MAX_CLOCK_SKEW_S - 60
    signed = context_hmac.sign_headers(hdrs, ts=old_ts)
    assert context_hmac.verify_headers({**hdrs, **signed}) is False


def test_deterministic_canonical(monkeypatch):
    monkeypatch.setenv("CONTEXT_HMAC_KEY", _SECRET)
    hdrs = {"X-Trace-ID": "abc-123", "X-Parent-Span-ID": "p"}
    s1 = context_hmac.sign_headers(hdrs, ts=1000)
    s2 = context_hmac.sign_headers(hdrs, ts=1000)
    assert s1 == s2
    assert s1["X-Governance-Timestamp"] == "1000"


def test_validate_compat_mode_returns_none(monkeypatch):
    monkeypatch.delenv("CONTEXT_HMAC_KEY", raising=False)
    assert context_hmac.validate_trace_headers({"X-Trace-ID": "x"}) is None


def test_validate_trusted_returns_context(monkeypatch):
    monkeypatch.setenv("CONTEXT_HMAC_KEY", _SECRET)
    hdrs = {"X-Trace-ID": "trusted-1", "X-Parent-Span-ID": "parent-2"}
    signed = context_hmac.sign_headers(hdrs)
    assert context_hmac.validate_trace_headers({**hdrs, **signed}) == \
        ("trusted-1", "parent-2")


def test_validate_forged_returns_empty(monkeypatch):
    monkeypatch.setenv("CONTEXT_HMAC_KEY", _SECRET)
    # 伪造签名（未签名头直接声明 trace）
    assert context_hmac.validate_trace_headers(
        {"X-Trace-ID": "evil-1"}) == ("", "")


# ── 2/2. 集成层（真实引擎 + 真实 HTTP）────────────────────────────────

class TestHmacEnabled(AioHTTPTestCase):
    """启用 CONTEXT_HMAC_KEY：伪造头降级，可信头保留，响应带签名。"""

    async def setUpAsync(self):
        os.environ["CONTEXT_HMAC_KEY"] = _SECRET
        await super().setUpAsync()

    async def tearDownAsync(self):
        await super().tearDownAsync()
        os.environ.pop("CONTEXT_HMAC_KEY", None)

    async def get_application(self):
        self._tmpdir = Path(tempfile.mkdtemp(prefix="hmac-on-"))
        self.addCleanup(shutil.rmtree, self._tmpdir, ignore_errors=True)
        return create_app(_write_empty_policy(self._tmpdir))

    @unittest_run_loop
    async def test_forged_trace_downgraded_to_new_root(self):
        resp = await self.client.post(
            "/v1/intercept",
            headers={"X-Trace-ID": "forged-999",
                     "X-Parent-Span-ID": "evil-parent"},
            json={"path": "/api/ok", "method": "GET", "body": {}})
        assert resp.status == 200
        out_trace = resp.headers.get("X-Trace-ID")
        # 伪造头被隔离: 响应 trace 是全新 UUID（非 "forged-999"），且无父链
        assert out_trace != "forged-999"
        assert len(out_trace) == 36  # UUID 格式

    @unittest_run_loop
    async def test_trusted_trace_preserved(self):
        hdrs = {"X-Trace-ID": "trusted-abc",
                "X-Parent-Span-ID": "parent-9"}
        hdrs.update(context_hmac.sign_headers(hdrs))
        resp = await self.client.post(
            "/v1/intercept", headers=hdrs,
            json={"path": "/api/ok", "method": "GET", "body": {}})
        assert resp.status == 200
        assert resp.headers.get("X-Trace-ID") == "trusted-abc"

    @unittest_run_loop
    async def test_response_carries_signature(self):
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/ok", "method": "GET", "body": {}})
        assert resp.status == 200
        assert resp.headers.get("X-Governance-Signature")
        assert resp.headers.get("X-Governance-Timestamp")


class TestHmacDisabledCompat(AioHTTPTestCase):
    """未启用（兼容模式）：行为与 v0.5.0 完全一致——信任传入 trace，无签名头。"""

    async def setUpAsync(self):
        os.environ.pop("CONTEXT_HMAC_KEY", None)
        await super().setUpAsync()

    async def get_application(self):
        self._tmpdir = Path(tempfile.mkdtemp(prefix="hmac-off-"))
        self.addCleanup(shutil.rmtree, self._tmpdir, ignore_errors=True)
        return create_app(_write_empty_policy(self._tmpdir))

    @unittest_run_loop
    async def test_compat_mode_trusts_trace_and_omits_signature(self):
        resp = await self.client.post(
            "/v1/intercept",
            headers={"X-Trace-ID": "compat-xyz"},
            json={"path": "/api/ok", "method": "GET", "body": {}})
        assert resp.status == 200
        assert resp.headers.get("X-Trace-ID") == "compat-xyz"
        assert "X-Governance-Signature" not in resp.headers
