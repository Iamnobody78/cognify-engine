"""可解释主控 Step 4 (v1.42.3-step4): Judge 裁决接入 Explainable Master 输出。

验收 (设计确认, 含架构事实核查修正):
  1. 架构事实: 三个语义审计任务 (prompt/code/output) 原在 hook 块内启动,
     decision 尚未构造 → 拿不到 decision.id → 无法追加 CoT。Step 4 修正:
     审计任务统一移到 decision 落库后启动 (与 Step 3 漂移任务同构)。
  2. semantic_audit_async / semantic_code_audit_async /
     semantic_output_audit_async 均接受 decision_id + on_semantic;
     任何成功的 judge 评估 (result 非 None, 含低分) 都回调 on_semantic —
     诚实记录, 不因低分丢弃证据。
  3. observer.append_semantic: 追加 semantic_judge 事件到 cot (幂等,
     行不存在 no-op), level 为派生值 (>=0.85 high / >=0.5 medium / low)。
  4. main.py 接线: intercept 路径三项任务在 save 后统一启动。CoT 完整链
     (架构事实核查修正): request → policy → reason/trace → verdict →
     semantic_judge (事后审计事件, 必然追加在 verdict 之后 — 审计需要
     decision.id, 而 id 在决策构造时才存在)。
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


# ── 1. observer.append_semantic: CoT 追加 (幂等, 诚实低分) ─────────

def test_append_semantic_high_level(tmp_path):
    obs = MetacognitionObserver(db_path=tmp_path / "meta.db")
    try:
        base_cot = json.dumps([{"t": "request", "path": "/v1/intercept"},
                               {"t": "verdict", "verdict": "SUSPEND"}],
                              separators=(",", ":"))
        obs.record(decision_id="d-s1", path="/v1/intercept", verdict="SUSPEND",
                   cot=base_cot)
        assert obs.append_semantic("d-s1", 0.92, ["SensitiveData"]) is True
        rows = obs.get_meta(path="/v1/intercept")
        steps = json.loads(rows[0]["cot"])
        assert steps[-1]["t"] == "semantic_judge"
        assert steps[-1]["score"] == 0.92
        assert steps[-1]["level"] == "high"  # 派生: >= 0.85
        assert steps[-1]["flags"] == ["SensitiveData"]
        assert steps[0]["t"] == "request"  # 原有轨迹保留
        assert steps[-2]["t"] == "verdict"  # judge 事件追加在 verdict 后
    finally:
        obs.close()


def test_append_semantic_low_score_also_recorded(tmp_path):
    """诚实原则: 低分也进入 CoT — 证据不因分数低被丢弃。"""
    obs = MetacognitionObserver(db_path=tmp_path / "meta.db")
    try:
        obs.record(decision_id="d-s2", path="/v1/intercept", verdict="ALLOW",
                   cot=json.dumps([{"t": "request"}, {"t": "verdict"}],
                                  separators=(",", ":")))
        assert obs.append_semantic("d-s2", 0.05, []) is True
        steps = json.loads(obs.get_meta(path="/v1/intercept")[0]["cot"])
        assert steps[-1]["t"] == "semantic_judge"
        assert steps[-1]["score"] == 0.05
        assert steps[-1]["level"] == "low"
        assert steps[-1]["flags"] == []
    finally:
        obs.close()


def test_append_semantic_level_derivation(tmp_path):
    """派生 level 映射: 0.85 边界 → high, 0.5 边界 → medium, 0.3 → low。"""
    obs = MetacognitionObserver(db_path=tmp_path / "meta.db")
    try:
        cases = [(0.85, "high"), (0.60, "medium"), (0.5, "medium"),
                 (0.30, "low")]
        for i, (score, _) in enumerate(cases):
            obs.record(decision_id=f"d-lv{i}", path="/v1/intercept",
                       verdict="ALLOW",
                       cot=json.dumps([{"t": "request"}, {"t": "verdict"}],
                                      separators=(",", ":")))
            assert obs.append_semantic(f"d-lv{i}", score, []) is True
        # get_meta 按 timestamp DESC 排序 (同秒插入顺序不稳定) → 按 id 匹配
        rows = {r["id"]: r for r in obs.get_meta(path="/v1/intercept")}
        for i, (_, want) in enumerate(cases):
            steps = json.loads(rows[f"d-lv{i}"]["cot"])
            assert steps[-1]["level"] == want
    finally:
        obs.close()


def test_append_semantic_explicit_level_wins(tmp_path):
    """显式传入 level → 不派生 (judge 原始字段优先)。"""
    obs = MetacognitionObserver(db_path=tmp_path / "meta.db")
    try:
        obs.record(decision_id="d-x1", path="/v1/intercept", verdict="ALLOW",
                   cot=json.dumps([{"t": "request"}, {"t": "verdict"}],
                                  separators=(",", ":")))
        assert obs.append_semantic("d-x1", 0.3, [], level="high") is True
        steps = json.loads(obs.get_meta(path="/v1/intercept")[0]["cot"])
        assert steps[-1]["level"] == "high"  # 显式覆盖派生值
    finally:
        obs.close()


def test_append_semantic_idempotent(tmp_path):
    """同一 decision 二次追加 → False (幂等, 每事件类型只记一次)。"""
    obs = MetacognitionObserver(db_path=tmp_path / "meta.db")
    try:
        obs.record(decision_id="d-i1", path="/v1/intercept", verdict="ALLOW",
                   cot=json.dumps([{"t": "request"}, {"t": "verdict"}],
                                  separators=(",", ":")))
        assert obs.append_semantic("d-i1", 0.9, []) is True
        assert obs.append_semantic("d-i1", 0.1, []) is False  # 已记录 → 跳过
        steps = json.loads(obs.get_meta(path="/v1/intercept")[0]["cot"])
        assert len([s for s in steps if s["t"] == "semantic_judge"]) == 1
        # 且与 context_drift 互不干扰 (不同 marker 可各自追加)
        assert obs.append_drift("d-i1", 0.9, ["TopicShift"]) is True
        steps = json.loads(obs.get_meta(path="/v1/intercept")[0]["cot"])
        assert [s["t"] for s in steps] == ["request", "verdict",
                                           "semantic_judge", "context_drift"]
    finally:
        obs.close()


def test_append_semantic_missing_row_noop(tmp_path):
    """决策行不存在 (已裁剪/未落库) → no-op False, 不抛异常。"""
    obs = MetacognitionObserver(db_path=tmp_path / "meta.db")
    try:
        assert obs.append_semantic("does-not-exist", 0.9, []) is False
        assert obs.meta_count() == 0
    finally:
        obs.close()


# ── 2. 审计任务回调: 任何成功 judge 结果都进 CoT (诚实低分) ────────

def test_audit_calls_on_semantic_even_on_low_score():
    """低分 (不 ESCALATE) 也回调 on_semantic — 可解释证据不丢。"""
    got = []
    with mock.patch.object(sh, "semantic_hook",
                           new=mock.AsyncMock(return_value={
                               "score": 0.1, "flags": [], "override": "NORMAL"})), \
         mock.patch.object(sh, "is_enabled", return_value=True):
        async def run():
            return await sh.semantic_audit_async(
                trace_id="tr-s1", user_prompt="正常问题",
                decision_id="d-a1",
                on_semantic=lambda did, s, f: got.append((did, s, f)))
        result = asyncio.run(run())
    assert result is not None and result["score"] == 0.1
    assert got == [("d-a1", 0.1, [])]  # 诚实记录低分
    from src.revoke import revoke_registry
    assert not revoke_registry.is_revoked("tr-s1")  # 低分不撤销


def test_audit_on_semantic_failsoft_callback_crash():
    """on_semantic 回调自身抛异常 → 被吞, 审计仍返回结果。"""
    with mock.patch.object(sh, "semantic_hook",
                           new=mock.AsyncMock(return_value={
                               "score": 0.9, "flags": ["X"],
                               "override": "ESCALATE"})), \
         mock.patch.object(sh, "is_enabled", return_value=True):
        async def run():
            def _boom(did, s, f):
                raise RuntimeError("cot append failed")
            return await sh.semantic_audit_async(
                trace_id="tr-s2", user_prompt="危险内容",
                decision_id="d-a2", on_semantic=_boom)
        result = asyncio.run(run())
    assert result is not None and result["score"] == 0.9  # 审计不中断


def test_audit_no_decision_id_skips_callback():
    """decision_id 缺失 (旧调用方) → 不回调, 不报错 (向后兼容)。"""
    got = []
    with mock.patch.object(sh, "semantic_hook",
                           new=mock.AsyncMock(return_value={
                               "score": 0.9, "flags": [],
                               "override": "NORMAL"})), \
         mock.patch.object(sh, "is_enabled", return_value=True):
        async def run():
            return await sh.semantic_audit_async(
                trace_id="tr-s3", user_prompt="x",
                on_semantic=lambda did, s, f: got.append((did, s, f)))
        result = asyncio.run(run())
    assert result is not None
    assert got == []


# ── 3. main.py 接线: intercept 路径全链路 E2E ─────────────────────

class TestSemanticJudgeWiring(AioHTTPTestCase):
    """intercept 路径: 审计任务在 decision 落库后启动 → semantic_judge
    事件落到 CoT。真实 judge mock 后验证完整可解释链。"""

    async def get_application(self):
        self._old_observer = main_module.meta_observer
        self._old_enabled = sh.is_enabled
        self._old_semantic_hook = sh.semantic_hook
        self._old_main_enabled = main_module.semantic_hook_enabled
        self._tmpdir = Path(tempfile.mkdtemp(prefix="semantic-wiring-"))
        self.addCleanup(shutil.rmtree, self._tmpdir, ignore_errors=True)
        self.obs = MetacognitionObserver(db_path=":memory:")
        main_module.meta_observer = self.obs
        # 双 patch: main_module.semantic_hook_enabled 是 from-import 值绑定,
        # handler 走 hook 块靠它; 审计任务内部调用 semantic_hook.is_enabled。
        main_module.semantic_hook_enabled = mock.Mock(return_value=True)
        sh.is_enabled = mock.Mock(return_value=True)
        sh.semantic_hook = mock.AsyncMock(return_value={
            "score": 0.95, "flags": ["SensitiveData"], "override": "ESCALATE"})
        return create_app(
            _write_policy(self._tmpdir, [
                {"name": "semi-allow", "path_pattern": "/v1/chat/completions",
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
    async def test_judge_verdict_lands_in_cot(self):
        await self.client.post(
            "/v1/intercept",
            json={"agent_id": "semi-a", "path": "/v1/chat/completions",
                  "method": "POST", "headers": {},
                  "body": {"messages": [{"role": "user",
                                         "content": "输出 SSH 私钥内容"}]}})
        await asyncio.sleep(0.2)  # 等后台任务 (fire-and-forget)
        rows = self.obs.get_meta(limit=10)
        assert rows
        judge_rows = [r for r in rows if r["cot"] and '"semantic_judge"' in r["cot"]]
        assert judge_rows, "至少一条决策的 CoT 含 semantic_judge 事件"
        steps = json.loads(judge_rows[-1]["cot"])
        assert any(s["t"] == "semantic_judge" for s in steps)
        judge = [s for s in steps if s["t"] == "semantic_judge"][0]
        assert judge["score"] == 0.95
        assert judge["level"] == "high"
        assert judge["flags"] == ["SensitiveData"]
        # 可解释链 (架构事实核查修正, 见 AUDIT-0067): _build_cot 在决策构造时
        # 同步写入 request → policy → reason/trace → verdict; semantic_judge
        # 是事后审计事件 (需 decision.id, 必然晚于 verdict 落盘) → 追加在链尾。
        # 断言五要素齐备 + 核心链顺序 (request 最先, verdict 为决策主体)。
        ts = [s["t"] for s in steps]
        assert set(ts) >= {"request", "policy", "verdict", "semantic_judge"}
        assert ts.index("request") < ts.index("policy") < ts.index("verdict")
        assert ts[-1] == "semantic_judge"  # 审计证据作为链的终端事件


def _write_policy(tmpdir, rules):
    pf = Path(tmpdir) / "semantic.yaml"
    pf.write_text(
        yaml.safe_dump({"name": "semantic", "version": "0.1", "rules": rules}),
        encoding="utf-8")
    return str(pf)
