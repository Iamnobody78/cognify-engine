# GATE2-APPROVED: governance-brain v1
"""治理大脑 Phase 1 测试（TASK-REAL-012 Phase 4）。

验收:
  1. 五级判定响应: ALLOW / ALLOW_WITH_WARNING / ESCALATE / DENY / SUSPEND
  2. rationale 可解释字段: 决策持久化含 rationale（为什么这么判）
  3. ALLOW_WITH_WARNING: 200 放行 + X-Governance-Warning 响应头
  4. SUSPEND: 403 拒绝（挂起审查语义）
  5. storage 无损迁移 12 列 → 13 列（rationale）
"""

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest
import yaml
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.main import create_app  # noqa: E402
from src.models import Verdict  # noqa: E402
from src.policy import PolicyEngine, VALID_ACTIONS, Rule  # noqa: E402
from src.storage import Storage  # noqa: E402


# ── 1. 五级判定枚举与策略支持 ────────────────────────────────────────

def test_verdict_has_five_levels():
    levels = set(Verdict)
    assert Verdict.ALLOW in levels
    assert Verdict.ALLOW_WITH_WARNING in levels
    assert Verdict.ESCALATE in levels
    assert Verdict.DENY in levels
    assert Verdict.SUSPEND in levels


def test_policy_valid_actions_include_new_levels():
    assert "ALLOW_WITH_WARNING" in VALID_ACTIONS
    assert "SUSPEND" in VALID_ACTIONS


def test_policy_loads_warning_and_suspend_rules(tmp_path):
    pf = tmp_path / "brain.yaml"
    pf.write_text(yaml.safe_dump({
        "name": "brain", "version": "0.1",
        "rules": [
            {"name": "warn-rule", "path_pattern": "/api/warn",
             "method": "GET", "action": "ALLOW_WITH_WARNING",
             "reason": "风险操作，放行但警告"},
            {"name": "suspend-rule", "path_pattern": "/api/sus",
             "method": "POST", "action": "SUSPEND",
             "reason": "挂起待人工审查"},
        ],
    }), encoding="utf-8")
    engine = PolicyEngine(str(pf))
    hit1 = engine.evaluate("/api/warn", "GET")
    assert hit1 is not None and hit1.action == "ALLOW_WITH_WARNING"
    hit2 = engine.evaluate("/api/sus", "POST")
    assert hit2 is not None and hit2.action == "SUSPEND"


# ── 2. rationale 持久化 + 13 列迁移 ─────────────────────────────────

def _full_dict(decision_id, verdict="DENY", rationale="rule=test"):
    return {
        "id": decision_id, "verdict": verdict, "reason": "r",
        "matched_rule": "test", "timestamp": "2026-08-03T00:00:00+00:00",
        "path": "/api/x", "method": "POST", "agent_id": "a",
        "tool_name": None, "tool_lethality": None,
        "trace_id": None, "parent_span_id": None, "rationale": rationale,
    }


def test_storage_fresh_schema_has_rationale_column():
    st = Storage(db_path=":memory:")
    cols = [r[1] for r in st.conn.execute("PRAGMA table_info(decisions)")]
    assert "rationale" in cols
    assert len(cols) == 13


def test_storage_save_get_rationale_roundtrip():
    st = Storage(db_path=":memory:")
    st.save(_full_dict("rb-1", rationale="rule=warn-rule"))
    rec = st.get_recent(limit=10)[0]
    assert rec["rationale"] == "rule=warn-rule"


def test_storage_migrates_12col_legacy_to_13col(tmp_path):
    # 构造 REAL-011 时代 12 列旧库 → 打开应无损补 rationale 列
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db))
    conn.execute("""
        CREATE TABLE decisions (
            id TEXT PRIMARY KEY, verdict TEXT NOT NULL, reason TEXT NOT NULL,
            matched_rule TEXT, timestamp TEXT NOT NULL, path TEXT NOT NULL,
            method TEXT NOT NULL, agent_id TEXT, tool_name TEXT,
            tool_lethality REAL, trace_id TEXT, parent_span_id TEXT)
    """)
    conn.execute("""INSERT INTO decisions VALUES
        ('legacy-1','DENY','r','m','2026-08-03T00:00:00+00:00','/api/x','POST',
         'a',NULL,NULL,NULL,NULL)""")
    conn.commit()
    conn.close()

    st = Storage(db_path=str(db))
    cols = [r[1] for r in st.conn.execute("PRAGMA table_info(decisions)")]
    assert "rationale" in cols
    assert len(cols) == 13
    rec = st.get_recent(limit=10)[0]
    assert rec["id"] == "legacy-1"      # 数据保留（无损）
    assert rec["rationale"] is None      # 旧行默认 NULL


# ── 3/4. HTTP 五级响应（真实引擎 + 临时策略文件）──────────────────────

def _write_brain_policy(tmpdir, rules):
    """写临时策略 YAML，返回路径。测试用真实 PolicyEngine 加载（与
    test_intercept.py 惯例一致 — 走通 YAML→Rule→evaluate→五级响应全链路）。"""
    pf = Path(tmpdir) / "brain.yaml"
    pf.write_text(
        yaml.safe_dump({"name": "brain", "version": "0.1", "rules": rules}),
        encoding="utf-8",
    )
    return str(pf)


class TestAllowWithWarning(AioHTTPTestCase):
    async def get_application(self):
        import src.main as main_mod
        self._tmpdir = Path(tempfile.mkdtemp(prefix="brain-aww-"))
        self.addCleanup(shutil.rmtree, self._tmpdir, ignore_errors=True)
        # 指向不可达端口 → _proxy_forward 立即失败返回 None，不阻塞 200 + 头
        main_mod.AGENT_BACKEND_URL = "http://127.0.0.1:1"
        return create_app(_write_brain_policy(self._tmpdir, [
            {"name": "warn-probe", "path_pattern": "/api/warn", "method": "GET",
             "action": "ALLOW_WITH_WARNING", "reason": "风险操作，放行但警告"},
        ]))

    @unittest_run_loop
    async def test_intercept_warning_allows_with_header(self):
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/warn", "method": "GET", "body": {}})
        assert resp.status == 200
        assert resp.headers.get("X-Governance-Warning") == "风险操作，放行但警告"
        data = await resp.json()
        assert data["verdict"] == "ALLOW_WITH_WARNING"


class TestSuspend(AioHTTPTestCase):
    async def get_application(self):
        self._tmpdir = Path(tempfile.mkdtemp(prefix="brain-sus-"))
        self.addCleanup(shutil.rmtree, self._tmpdir, ignore_errors=True)
        return create_app(_write_brain_policy(self._tmpdir, [
            {"name": "suspend-probe", "path_pattern": "/api/sus", "method": "POST",
             "action": "SUSPEND", "reason": "挂起待人工审查"},
        ]))

    @unittest_run_loop
    async def test_intercept_suspend_denies_403(self):
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/sus", "method": "POST", "body": {}})
        assert resp.status == 403
        data = await resp.json()
        assert data["verdict"] == "SUSPEND"


class TestChatSuspend(AioHTTPTestCase):
    """chat 路径 SUSPEND — 拒绝转发（403 + governance_denied），无需上游。"""

    async def get_application(self):
        self._tmpdir = Path(tempfile.mkdtemp(prefix="brain-chatsus-"))
        self.addCleanup(shutil.rmtree, self._tmpdir, ignore_errors=True)
        return create_app(_write_brain_policy(self._tmpdir, [
            {"name": "chat-suspend", "path_pattern": "/v1/chat/completions",
             "method": "POST", "action": "SUSPEND", "reason": "chat 挂起"},
        ]))

    @unittest_run_loop
    async def test_chat_suspend_denies_403(self):
        resp = await self.client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o",
                  "messages": [{"role": "user", "content": "hi"}]})
        assert resp.status == 403
        data = await resp.json()
        assert data["error"]["message"] == "chat 挂起"


class TestChatWarningWithUpstream(AioHTTPTestCase):
    """chat 路径 ALLOW_WITH_WARNING — 200 + 警告头 + 真实转发上游（模拟 LLM）。"""

    async def get_application(self):
        import src.main as main_mod
        import aiohttp.web as aio_web
        self._tmpdir = Path(tempfile.mkdtemp(prefix="brain-chatwarn-"))
        self.addCleanup(shutil.rmtree, self._tmpdir, ignore_errors=True)

        # 临时上游 LLM：返回 OpenAI 兼容 JSON
        up = aio_web.Application()

        async def _llm(request):
            return aio_web.json_response({
                "id": "cmpl-brain", "object": "chat.completion",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            })

        up.router.add_post("/v1/chat/completions", _llm)
        runner = aio_web.AppRunner(up)
        await runner.setup()
        site = aio_web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        self._upstream_runner = runner
        port = site._server.sockets[0].getsockname()[1]
        main_mod.AGENT_BACKEND_URL = f"http://127.0.0.1:{port}"

        return create_app(_write_brain_policy(self._tmpdir, [
            {"name": "chat-warn", "path_pattern": "/v1/chat/completions",
             "method": "POST", "action": "ALLOW_WITH_WARNING", "reason": "chat 放行但警告"},
        ]))

    async def tearDownAsync(self):
        await super().tearDownAsync()
        if getattr(self, "_upstream_runner", None) is not None:
            await self._upstream_runner.cleanup()

    @unittest_run_loop
    async def test_chat_warning_forwards_with_header(self):
        resp = await self.client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o",
                  "messages": [{"role": "user", "content": "hi"}]})
        assert resp.status == 200
        assert resp.headers.get("X-Governance-Warning") == "chat 放行但警告"
        data = await resp.json()
        # 上游真实响应被透传（验证 ALLOW_WITH_WARNING 转发语义未破坏）
        assert data["id"] == "cmpl-brain"
