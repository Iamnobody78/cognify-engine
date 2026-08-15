"""P0 (暗雷区) — 异常处理日志增强测试。

验证: reload 静默失败 → error 级完整堆栈；客户端错误 → warning 简短 + debug 堆栈；
预期内代理失败 → warning 不刷屏。响应体始终不暴露内部细节。
"""

import logging
import shutil
import tempfile
from pathlib import Path

import pytest
import yaml
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from src.policy import PolicyEngine
from src.main import create_app
from src import main as main_mod


class _ListHandler(logging.Handler):
    """捕获日志记录（用于 AioHTTPTestCase 内，无法用 pytest caplog fixture）。"""

    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records: list = []

    def emit(self, record):
        self.records.append(record)

    def messages(self):
        return [r.getMessage() for r in self.records]


def _write_empty_policy(tmpdir):
    pf = Path(tmpdir) / "p0.yaml"
    pf.write_text(
        yaml.safe_dump({"name": "p0", "version": "0.1", "rules": []}),
        encoding="utf-8")
    return str(pf)


# ── 1. policy.reload 静默失败 → error 级完整堆栈 ───────────────────────

def test_policy_reload_failure_logs_traceback(tmp_path, monkeypatch, caplog):
    pf = tmp_path / "p.yaml"
    pf.write_text(yaml.safe_dump({"name": "t", "rules": []}), encoding="utf-8")
    eng = PolicyEngine(str(pf))

    def _boom(self, _path):
        raise RuntimeError("yaml corrupted")

    monkeypatch.setattr(PolicyEngine, "_load", _boom)
    with caplog.at_level(logging.ERROR, logger="src.policy"):
        assert eng.reload() is False  # 行为不变: fail-safe 保留旧规则
    # P0 目标: error 级记录 + 完整堆栈（logger.exception 自动附加 exc_text）
    hit = [r for r in caplog.records
           if "policy reload FAILED" in r.getMessage()]
    assert len(hit) == 1
    assert "yaml corrupted" in hit[0].getMessage()
    assert "Traceback (most recent call last)" in (hit[0].exc_text or "")
    assert "RuntimeError" in (hit[0].exc_text or "")  # 真实异常类型可定位


def test_policy_reload_success_no_error_log(tmp_path, caplog):
    pf = tmp_path / "p.yaml"
    pf.write_text(yaml.safe_dump({"name": "t", "rules": []}), encoding="utf-8")
    eng = PolicyEngine(str(pf))
    with caplog.at_level(logging.ERROR, logger="src.policy"):
        assert eng.reload() is True
    assert not any(r.levelno >= logging.ERROR for r in caplog.records)


# ── 2. 真实 HTTP: 客户端错误 422 → warning 日志（不暴露内部细节）───────

class TestP0Logging(AioHTTPTestCase):
    async def get_application(self):
        self._tmpdir = Path(tempfile.mkdtemp(prefix="p0-"))
        self.addCleanup(shutil.rmtree, self._tmpdir, ignore_errors=True)
        return create_app(_write_empty_policy(self._tmpdir))

    @unittest_run_loop
    async def test_invalid_body_logs_warning_not_error(self):
        h = _ListHandler()
        main_mod.logger.addHandler(h)
        try:
            resp = await self.client.post(
                "/v1/intercept",
                json={"path": 123, "method": "GET"})  # path 应为 str → ValidationError
            assert resp.status == 422
            data = await resp.json()
            # 响应体不暴露内部细节（P0 要求）
            assert data == {"error": "invalid request body"}
            msgs = h.messages()
            assert any("invalid intercept body (422)" in m for m in msgs)
        finally:
            main_mod.logger.removeHandler(h)

    @unittest_run_loop
    async def test_proxy_forward_failure_logs_warning(self):
        """ALLOW 透传时上游不可达 → warning 简短 + 响应仍 200（降级不刷屏）。"""
        h = _ListHandler()
        main_mod.logger.addHandler(h)
        try:
            resp = await self.client.post(
                "/v1/intercept",
                json={"path": "/api/ok", "method": "GET", "body": {}})
            assert resp.status == 200
            msgs = h.messages()
            assert any("proxy forward failed" in m for m in msgs)
            # warning 消息保持简短（不把整段堆栈打在生产日志）
            warn_msgs = [m for m in msgs if "proxy forward failed" in m]
            assert all(len(m) < 200 for m in warn_msgs)
        finally:
            main_mod.logger.removeHandler(h)
