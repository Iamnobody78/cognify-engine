"""可解释主控 Step 2 (v1.42.1-step2): CoT 决策轨迹回放 → decision_meta.cot。

验收 (设计确认):
  1. _build_cot: 生成有界 JSON 轨迹 (request 特征 → policy 命中 → 附加闸门
     → 最终裁决), 诚实回放 (非 LLM 事后解释), 截断上限 COT_MAX_CHARS
  2. record(cot=...): cot 落库 decision_meta.cot, get_meta 可读回
  3. 迁移: 老库 (无 cot 列) → _init_db 幂等 ALTER ADD COLUMN, 数据不丢
  4. 接线: main.py 决策路径 (intercept/deny/chat) 在 storage.save 后
     fail-soft 调用 record(cot=...); GOV_META_DB env 或 override 启用
  5. fail-soft: observer 异常 → 主路径不受影响 (仍返回正常响应)
"""

import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

import yaml
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import src.main as main_module  # noqa: E402
from src.main import create_app  # noqa: E402
from src.metacognition.observer import MetacognitionObserver  # noqa: E402


def _write_policy(tmpdir, rules):
    """写临时策略 YAML (真实 PolicyEngine 全链路, 与 test_governance_brain 同惯例)。"""
    pf = Path(tmpdir) / "cot.yaml"
    pf.write_text(
        yaml.safe_dump({"name": "cot", "version": "0.1", "rules": rules}),
        encoding="utf-8",
    )
    return str(pf)


# ── 1. CoT 链构建 ────────────────────────────────────────────────

def test_build_cot_full_chain():
    """完整轨迹: request → policy → reason/trace → verdict。"""
    cot = main_module._build_cot(
        method="POST",
        path="/v1/intercept",
        matched_rule="dangerous-tools",
        verdict="DENY",
        reason="匹配规则 'dangerous-tools' → 拦截",
        trace_id="tr-1",
        tool_name="rm",
        tool_lethality=0.9,
    )
    steps = json.loads(cot)
    types = [s["t"] for s in steps]
    assert types == ["request", "policy", "reason", "trace", "verdict"]
    assert steps[0]["path"] == "/v1/intercept"
    assert steps[0]["tool"] == "rm"
    assert steps[0]["lethality"] == 0.9
    assert steps[1]["matched_rule"] == "dangerous-tools"
    assert steps[1]["action"] == "DENY"
    assert steps[-1]["verdict"] == "DENY"


def test_build_cot_minimal_and_bounded():
    """最小轨迹 (无 reason/trace/tool) + 有界截断 (超长 reason 不撑爆)。"""
    cot = main_module._build_cot(
        method="GET", path="/api/x", matched_rule=None, verdict="ALLOW",
        reason="x" * 5000,
    )
    steps = json.loads(cot)
    assert len(steps) == 4  # request / policy / reason(截断) / verdict
    assert len(cot) <= main_module.COT_MAX_CHARS
    # 超长 reason 必须被截断到 500 字符以内
    reason_step = [s for s in steps if s["t"] == "reason"][0]
    assert len(reason_step["text"]) <= 500


def test_build_cot_no_llm_fabrication():
    """诚实回放: 只有真实事件节点, 无 LLM 编造字段。"""
    cot = main_module._build_cot(
        method="POST", path="/v1/chat/completions",
        matched_rule="allow-chat", verdict="ALLOW_WITH_WARNING",
        reason="匹配规则 'allow-chat' → 放行但警告",
    )
    steps = json.loads(cot)
    allowed_keys = {"t", "method", "path", "tool", "lethality",
                    "matched_rule", "action", "text", "trace_id", "verdict"}
    for step in steps:
        assert set(step.keys()) <= allowed_keys, f"unexpected keys: {step}"


# ── 2. record(cot=...) 落库 ──────────────────────────────────────

def test_record_persists_cot(tmp_path):
    obs = MetacognitionObserver(db_path=tmp_path / "meta.db")
    try:
        cot = json.dumps([{"t": "request", "path": "/v1/intercept"},
                          {"t": "verdict", "verdict": "DENY"}])
        obs.record(decision_id="d-cot-1", path="/v1/intercept",
                   verdict="DENY", cot=cot)
        rows = obs.get_meta(path="/v1/intercept")
        assert len(rows) == 1
        assert rows[0]["cot"] == cot
        # record 返回值: 冷启动不触发偏差 (与 v1.39.1 契约一致)
    finally:
        obs.close()


# ── 3. 迁移: 老库无 cot 列 → 幂等 ALTER ────────────────────────────

def test_migration_adds_cot_column_idempotent(tmp_path):
    """v1.39.1 老库 (10 列无 cot) → 新代码初始化 → cot 列存在且数据保留。"""
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE decision_meta (
        id TEXT PRIMARY KEY, trace_id TEXT, path TEXT NOT NULL,
        method TEXT, verdict TEXT NOT NULL, matched_rule TEXT,
        confidence REAL, deviation REAL, event TEXT,
        timestamp TEXT NOT NULL)""")
    conn.execute(
        "INSERT INTO decision_meta (id, path, verdict, timestamp) "
        "VALUES ('d-old', '/v1/chat', 'ALLOW', '2026-08-05T00:00:00+00:00')")
    conn.commit()
    conn.close()

    obs = MetacognitionObserver(db_path=db)  # _init_db 触发迁移
    try:
        rows = obs.get_meta(path="/v1/chat")
        assert len(rows) == 1
        assert rows[0]["id"] == "d-old"  # 老数据保留
        assert "cot" in rows[0] and rows[0]["cot"] is None
        # 二次迁移幂等
        obs._migrate_locked()
        assert obs.meta_count() == 1
    finally:
        obs.close()


# ── 4. 接线: main.py 决策路径 → decision_meta.cot ─────────────────

class TestCotWiring(AioHTTPTestCase):
    """create_app(meta_observer_override=...) 启用观察层后, intercept/chat
    DENY 路径的 CoT 轨迹真实落库 (非单元测试 mock, 全链路集成)。
    命中 DENY 规则 → 不经上游转发 (避免 502)。"""

    async def get_application(self):
        self._old_observer = main_module.meta_observer
        self._tmpdir = Path(tempfile.mkdtemp(prefix="cot-wiring-"))
        self.addCleanup(shutil.rmtree, self._tmpdir, ignore_errors=True)
        self.obs = MetacognitionObserver(db_path=":memory:")
        main_module.meta_observer = self.obs  # _record_meta_soft 读模块全局
        return create_app(
            _write_policy(self._tmpdir, [
                {"name": "cot-deny", "path_pattern": "/v1/chat/completions",
                 "method": "POST", "action": "SUSPEND", "reason": "CoT 测试拦截"},
            ]),
            meta_observer_override=self.obs,
        )

    async def tearDownAsync(self):
        main_module.meta_observer = self._old_observer
        self.obs.close()
        await super().tearDownAsync()

    @unittest_run_loop
    async def test_intercept_deny_writes_cot(self):
        resp = await self.client.post(
            "/v1/intercept",
            json={
                "agent_id": "a1",
                "path": "/v1/chat/completions",
                "method": "POST",
                "headers": {},
                "body": {"messages": [{"role": "user", "content": "hi"}]},
            },
        )
        assert resp.status == 403  # 命中 cot-deny → DENY
        rows = self.obs.get_meta(limit=10)
        assert rows, "intercept 决策必须写入 decision_meta"
        row = rows[0]
        assert row["cot"], "cot 轨迹必须非空"
        steps = json.loads(row["cot"])
        assert steps[0]["t"] == "request"
        # intercept 语义: req.path = body 中的代理目标路径 (非 URL)
        assert steps[0]["path"] == "/v1/chat/completions"
        # policy 步骤必须记录真实命中规则
        policy = [s for s in steps if s["t"] == "policy"][0]
        assert policy["matched_rule"] == "cot-deny"
        assert policy["action"] == "SUSPEND"
        assert steps[-1]["t"] == "verdict"
        assert steps[-1]["verdict"] == row["verdict"]  # 轨迹终态 = 落库裁决

    @unittest_run_loop
    async def test_chat_deny_writes_cot(self):
        resp = await self.client.post(
            "/v1/chat/completions",
            json={"model": "m",
                  "messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status == 403  # 命中 cot-deny → SUSPEND (无上游转发)
        rows = self.obs.get_meta(path="/v1/chat/completions", limit=5)
        assert rows, "chat 决策必须写入 decision_meta"
        assert all(r["cot"] for r in rows)
        steps = json.loads(rows[0]["cot"])
        policy = [s for s in steps if s["t"] == "policy"][0]
        assert policy["matched_rule"] == "cot-deny"
        assert policy["action"] == "SUSPEND"


# ── 5. fail-soft: observer 异常不阻断主路径 ───────────────────────

class TestCotFailSoft(AioHTTPTestCase):
    """observer.record 抛异常 → 网关主路径照常 (fail-soft 契约)。"""

    async def get_application(self):
        self._old_observer = main_module.meta_observer

        class _Broken:
            def record(self, **kwargs):
                raise RuntimeError("observer broken")

        main_module.meta_observer = _Broken()  # type: ignore[assignment]
        return create_app()

    async def tearDownAsync(self):
        main_module.meta_observer = self._old_observer
        await super().tearDownAsync()

    @unittest_run_loop
    async def test_broken_observer_does_not_break_gateway(self):
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/unknown", "method": "GET"},
        )
        assert resp.status == 200  # 主路径正常, 观察层异常仅 warning
        data = await resp.json()
        assert data["verdict"] == "ALLOW"
