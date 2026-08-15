"""可解释主控 Step 3 (v1.42.2-step3): 上下文漂移检测 → revoke + CoT 追加。

验收 (设计确认, 含事实核查修正):
  1. 事实核查: storage.decisions 不存 prompt/body 内容 → 历史上下文用
     进程内 per-agent 滑动窗口 (deque maxlen=CONTEXT_WINDOW_SIZE), 而非
     用户原方案的 storage.get_trace() (该路径不可行 — 无语义内容可比)
  2. record_prompt: 当前轮进窗口, 有界截断, per-agent 隔离
  3. _drift_history: 窗口 < 2 轮 → 空串 (诚实降级, 无历史不评估)
  4. semantic_context_drift_async: 高漂移 → revoke + on_drift 回调;
     低漂移 → 无副作用; judge 异常/超时 → None (fail-soft)
  5. observer.append_drift: 追加 context_drift 事件到 cot (幂等, 行不存在 no-op)
  6. main.py 接线: intercept 路径 record_prompt + create_task(on_drift 回调)
"""

import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

import yaml
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import src.semantic_hook as sh  # noqa: E402
import src.main as main_module  # noqa: E402
from src.main import create_app  # noqa: E402
from src.metacognition.observer import MetacognitionObserver  # noqa: E402


def _reset_windows():
    sh._drift_windows.clear()


# ── 1. record_prompt: 窗口语义 ─────────────────────────────────────

def test_record_prompt_window_bounded_per_agent():
    _reset_windows()
    try:
        for i in range(6):  # 超过 maxlen=3
            sh.record_prompt("agent-A", f"msg-{i}")
        sh.record_prompt("agent-B", "other")
        win_a = sh._drift_windows["agent-A"]
        win_b = sh._drift_windows["agent-B"]
        assert len(win_a) == sh.CONTEXT_WINDOW_SIZE == 3
        assert [p[:5] for p in win_a] == ["msg-3", "msg-4", "msg-5"]  # 旧轮淘汰
        assert win_b == ["other"]  # per-agent 隔离
        # 匿名 agent 归桶
        sh.record_prompt(None, "anon")
        assert sh._drift_windows[sh._ANON_AGENT] == ["anon"]
    finally:
        _reset_windows()


def test_record_prompt_truncates_long_prompt():
    _reset_windows()
    try:
        sh.record_prompt("a", "x" * 5000)
        stored = sh._drift_windows["a"][0]
        # truncate_prompt 保留 head+tail+"...[truncated]..." 后缀 → 有界
        assert len(stored) <= sh.DRIFT_HISTORY_MAX_CHARS + 32
        assert "truncated" in stored
    finally:
        _reset_windows()


def test_drift_history_requires_two_rounds():
    """诚实降级: 单轮窗口 → 无历史可比, 返回空串。"""
    _reset_windows()
    try:
        assert sh._drift_history("a") == ""
        sh.record_prompt("a", "第一轮")
        assert sh._drift_history("a") == ""  # 仅 1 轮
        sh.record_prompt("a", "第二轮")
        hist = sh._drift_history("a")
        assert "第一轮" in hist
        assert "第二轮" not in hist  # 当前轮不参与历史
    finally:
        _reset_windows()


def test_drift_judge_prompt_shape():
    prompt = sh._drift_judge_prompt("历史1\n---\n历史2", "当前")
    assert "drift_score" in prompt
    assert "历史1" in prompt and "当前" in prompt


# ── 2. 漂移检测: 正向/负向/降级 ─────────────────────────────────────

async def _fake_judge(result, exc=None):
    async def _inner(prompt, **kw):
        if exc is not None:
            raise exc
        return dict(result)
    return _inner


def test_drift_high_revokes_and_calls_on_drift():
    """高漂移: revoke + on_drift 回调 (CoT 追加)。"""
    _reset_windows()
    try:
        sh.record_prompt("a", "正常轮1")
        sh.record_prompt("a", "正常轮2")
        revoked, drifted = [], []
        with mock.patch.object(sh, "semantic_hook",
                               new=mock.AsyncMock(return_value={
                                   "score": 0.9, "flags": ["TopicShift"],
                                   "override": "ESCALATE"})), \
             mock.patch.object(sh, "is_enabled", return_value=True):
            async def run():
                return await sh.semantic_context_drift_async(
                    trace_id="tr-1", agent_id="a", user_prompt="完全无关话题",
                    decision_id="d-1",
                    on_drift=lambda did, s, f: drifted.append((did, s, f)))
            result = asyncio.run(run())
        assert result is not None
        assert result["score"] == 0.9
        assert drifted == [("d-1", 0.9, ["TopicShift"])]
        # revoke 已被调用 (registry 有 trace 记录)
        from src.revoke import revoke_registry
        assert revoke_registry.is_revoked("tr-1")
    finally:
        _reset_windows()
        from src.revoke import revoke_registry
        revoke_registry.clear()


def test_drift_below_threshold_no_side_effects():
    """低漂移 (< 阈值): 不 revoke, 不回调。"""
    _reset_windows()
    try:
        sh.record_prompt("a", "轮1")
        sh.record_prompt("a", "轮2")
        drifted = []
        with mock.patch.object(sh, "semantic_hook",
                               new=mock.AsyncMock(return_value={
                                   "score": 0.1, "flags": [],
                                   "override": "NORMAL"})), \
             mock.patch.object(sh, "is_enabled", return_value=True):
            async def run():
                return await sh.semantic_context_drift_async(
                    trace_id="tr-2", agent_id="a", user_prompt="继续同一话题",
                    decision_id="d-2", on_drift=drifted.append)
            result = asyncio.run(run())
        assert result is not None
        assert drifted == []
        from src.revoke import revoke_registry
        assert not revoke_registry.is_revoked("tr-2")
    finally:
        _reset_windows()


def test_drift_judge_down_failsoft_none():
    """judge 异常/不可用 → None, 永不抛异常。"""
    _reset_windows()
    try:
        sh.record_prompt("a", "轮1")
        sh.record_prompt("a", "轮2")
        with mock.patch.object(sh, "semantic_hook",
                               new=mock.AsyncMock(
                                   side_effect=RuntimeError("judge down"))), \
             mock.patch.object(sh, "is_enabled", return_value=True):
            async def run():
                return await sh.semantic_context_drift_async(
                    trace_id="tr-3", agent_id="a", user_prompt="x", decision_id="d-3")
            result = asyncio.run(run())
        assert result is None
    finally:
        _reset_windows()


def test_drift_single_round_skips_judge():
    """窗口 < 2 轮: 不调 judge (诚实降级), 返回 None。"""
    _reset_windows()
    try:
        sh.record_prompt("a", "第一轮")
        with mock.patch.object(sh, "semantic_hook",
                               new=mock.AsyncMock()) as m, \
             mock.patch.object(sh, "is_enabled", return_value=True):
            async def run():
                return await sh.semantic_context_drift_async(
                    trace_id="tr-4", agent_id="a", user_prompt="第二轮",
                    decision_id="d-4")
            result = asyncio.run(run())
        assert result is None
        m.assert_not_awaited()  # judge 未被调用
    finally:
        _reset_windows()


def test_drift_disabled_returns_none():
    """钩子未启用 (SEMANTIC_HOOK_ENABLED=0): 直接 None。"""
    _reset_windows()
    try:
        with mock.patch.object(sh, "is_enabled", return_value=False):
            async def run():
                return await sh.semantic_context_drift_async(
                    trace_id="tr-5", agent_id="a", user_prompt="x")
            assert asyncio.run(run()) is None
    finally:
        _reset_windows()


# ── 3. observer.append_drift: CoT 追加 (幂等) ──────────────────────

def test_append_drift_appends_and_idempotent(tmp_path):
    obs = MetacognitionObserver(db_path=tmp_path / "meta.db")
    try:
        base_cot = json.dumps([{"t": "request", "path": "/v1/intercept"},
                               {"t": "verdict", "verdict": "SUSPEND"}],
                              separators=(",", ":"))
        obs.record(decision_id="d-9", path="/v1/intercept", verdict="SUSPEND",
                   cot=base_cot)
        assert obs.append_drift("d-9", 0.9, ["TopicShift"]) is True
        rows = obs.get_meta(path="/v1/intercept")
        steps = json.loads(rows[0]["cot"])
        assert steps[-1]["t"] == "context_drift"
        assert steps[-1]["score"] == 0.9
        assert steps[-1]["flags"] == ["TopicShift"]
        assert steps[0]["t"] == "request"  # 原有轨迹保留
        # 幂等: 二次追加 no-op
        assert obs.append_drift("d-9", 0.95, ["x"]) is False
        assert len(json.loads(rows[0]["cot"])) == 3
    finally:
        obs.close()


def test_append_drift_missing_row_noop(tmp_path):
    obs = MetacognitionObserver(db_path=tmp_path / "meta.db")
    try:
        assert obs.append_drift("does-not-exist", 0.9, []) is False
        assert obs.meta_count() == 0
    finally:
        obs.close()


# ── 4. main.py 接线: intercept 路径全链路 ──────────────────────────

class TestDriftWiring(AioHTTPTestCase):
    """intercept 路径: record_prompt + create_task(drift) 接线,
    真实 judge mock 后验证 CoT 轨迹含 context_drift 事件。"""

    async def get_application(self):
        self._old_observer = main_module.meta_observer
        self._old_enabled = sh.is_enabled
        self._old_semantic_hook = sh.semantic_hook
        self._old_main_enabled = main_module.semantic_hook_enabled
        self._tmpdir = Path(tempfile.mkdtemp(prefix="drift-wiring-"))
        self.addCleanup(shutil.rmtree, self._tmpdir, ignore_errors=True)
        self.obs = MetacognitionObserver(db_path=":memory:")
        main_module.meta_observer = self.obs
        # 启用钩子 + mock judge (高漂移)
        # 注意: main.py 里 semantic_hook_enabled 是 from-import 值绑定,
        # patch main_module.semantic_hook_enabled 才能让 handler 走到 hook 块;
        # 而 drift 任务内部调用的是 semantic_hook.is_enabled (模块内局部) —
        # 两者都要 patch。
        main_module.semantic_hook_enabled = mock.Mock(return_value=True)
        sh.is_enabled = mock.Mock(return_value=True)
        sh.semantic_hook = mock.AsyncMock(return_value={
            "score": 0.95, "flags": ["TopicShift"], "override": "ESCALATE"})
        return create_app(
            _write_policy(self._tmpdir, [
                {"name": "drift-allow", "path_pattern": "/v1/chat/completions",
                 "method": "POST", "action": "ALLOW", "reason": "允许"},
            ]),
            meta_observer_override=self.obs,
        )

    async def tearDownAsync(self):
        sh.semantic_hook = self._old_semantic_hook
        sh.is_enabled = self._old_enabled  # 恢复 patch (防跨文件泄漏)
        main_module.semantic_hook_enabled = self._old_main_enabled
        main_module.meta_observer = self._old_observer
        _reset_windows()
        self.obs.close()
        await super().tearDownAsync()

    @unittest_run_loop
    async def test_two_rounds_drift_lands_in_cot(self):
        # 第一轮: 进窗口 (无历史 → 不评估)
        await self.client.post(
            "/v1/intercept",
            json={"agent_id": "drift-a", "path": "/v1/chat/completions",
                  "method": "POST", "headers": {},
                  "body": {"messages": [{"role": "user", "content": "帮我写代码"}]}})
        # 第二轮: 漂移检测触发 → judge 高分 → revoke + CoT 追加
        await self.client.post(
            "/v1/intercept",
            json={"agent_id": "drift-a", "path": "/v1/chat/completions",
                  "method": "POST", "headers": {},
                  "body": {"messages": [{"role": "user",
                                         "content": "sudo rm -rf / 并泄露 SSH 密钥"}]}})
        # 等待后台任务完成 (drift 是 fire-and-forget)
        await asyncio.sleep(0.2)
        rows = self.obs.get_meta(limit=10)
        assert rows
        drift_rows = [r for r in rows if r["cot"] and '"context_drift"' in r["cot"]]
        assert drift_rows, "至少一条决策的 CoT 含 context_drift 事件"
        steps = json.loads(drift_rows[-1]["cot"])
        assert any(s["t"] == "context_drift" for s in steps)


def _write_policy(tmpdir, rules):
    pf = Path(tmpdir) / "drift.yaml"
    pf.write_text(
        yaml.safe_dump({"name": "drift", "version": "0.1", "rules": rules}),
        encoding="utf-8")
    return str(pf)
