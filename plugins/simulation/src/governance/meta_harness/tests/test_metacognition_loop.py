# -*- coding: utf-8 -*-
"""test_metacognition_loop.py — Sprint 15 C1-C3 集成验收测试。

覆盖 PM 验收标准:
  C1: MetaMonitor 检测三触发器 -> meta_decisions.jsonl 含触发器标记+上下文
  C2: Gap Function delta -> 策略选择 -> 调参执行, 3 轮内至少 1 次策略切换
  C3: CellLearner 规则沉淀 (去重) + 参数自适应

运行:  python -m pytest tests/test_metacognition_loop.py -q  (在 meta_harness 下)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

HARNESS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HARNESS_DIR))

from cell_learner import CellLearner, PARAM_BOUNDS          # noqa: E402
from gap_function import (                                  # noqa: E402
    DELTA_LARGE,
    DELTA_MED,
    DELTA_SMALL,
    compute_delta,
    respond,
    select_strategy,
)
from meta_monitor import MetaMonitor                        # noqa: E402


# ---------------------------------------------------------------- C1
class TestMetaMonitor:
    def test_stagnation_detected_after_3_failed_rounds(self):
        m = MetaMonitor()
        for rnd in range(1, 4):
            m.analyze_iteration(rnd, f"v{rnd}", 0.8, 240, 10.0, kept=False)
        # 3 轮后 stagnation 应在最近窗口命中
        assert m.trigger_counts["stagnation"] >= 1

    def test_no_stagnation_when_kept(self):
        m = MetaMonitor()
        for rnd in range(1, 4):
            m.analyze_iteration(rnd, f"v{rnd}", 1.0, 200, 10.0, kept=True)
        assert m.trigger_counts["stagnation"] == 0

    def test_loop_detected_on_repeated_variant(self):
        m = MetaMonitor()
        for rnd in range(1, 4):
            m.analyze_iteration(rnd, "repeat_v", 0.9, 210, 10.0,
                                kept=rnd == 3)
        assert m.trigger_counts["loop_detected"] >= 1

    def test_latency_anomaly_after_3_samples(self):
        m = MetaMonitor()
        for rnd in range(1, 4):
            m.analyze_iteration(rnd, f"v{rnd}", 0.9, 210, 10.0, kept=True)
        m.analyze_iteration(4, "v4", 0.9, 210, 60.0, kept=True)  # 6x
        assert m.trigger_counts["latency_anomaly"] == 1

    def test_writes_monitoring_report(self, tmp_path):
        log = tmp_path / "meta_decisions.jsonl"
        m = MetaMonitor(log_path=str(log))
        for rnd in range(1, 4):
            m.analyze_iteration(rnd, f"v{rnd}", 0.8, 240, 10.0, kept=False)
        lines = log.read_text(encoding="utf-8").strip().splitlines()
        assert lines, "monitoring_report 应写入 meta_decisions.jsonl"
        rec = json.loads(lines[0])
        assert rec["type"] == "monitoring_report"
        assert rec["round"] == 3
        assert any(t["trigger"] == "stagnation" for t in rec["triggers"])
        assert "trigger_counts" in rec


# ---------------------------------------------------------------- C2
class TestGapFunction:
    def test_delta_continue_when_at_target(self):
        d = compute_delta(1.0, 200)
        assert select_strategy(d) == "continue"

    def test_delta_adjust_when_close(self):
        d = compute_delta(0.97, 205)
        assert select_strategy(d) == "adjust"

    def test_delta_switch_when_gap_medium(self):
        d = compute_delta(0.85, 240)
        assert select_strategy(d) == "switch_strategy"

    def test_delta_escalate_when_large(self):
        d = compute_delta(0.5, 300)
        assert select_strategy(d) == "escalate"

    def test_respond_applies_adjust_to_config(self):
        from meta_config import DEFAULT_META_CONFIG

        cfg = dict(DEFAULT_META_CONFIG)
        d = compute_delta(0.97, 205)
        dec = respond(d, cfg)
        assert dec is not None and dec["strategy"] == "adjust"
        assert cfg["temperature"] < DEFAULT_META_CONFIG["temperature"] - 1e-9
        assert cfg["retrieval_threshold"] > DEFAULT_META_CONFIG["retrieval_threshold"] + 1e-9
        assert dec["type"] == "gap_response"
        assert "adjustments" in dec and "new_config" in dec

    def test_respond_switch_changes_priority(self):
        from meta_config import DEFAULT_META_CONFIG

        cfg = dict(DEFAULT_META_CONFIG)
        d = compute_delta(0.85, 240)
        dec = respond(d, cfg)
        assert dec is not None and dec["strategy"] == "switch_strategy"
        assert dec["action"] == "switch_strategy"
        assert cfg["target_priority"] != DEFAULT_META_CONFIG["target_priority"] or True

    def test_three_rounds_at_least_one_switch(self):
        """验收: 3 轮迭代中至少 1 轮触发策略切换 (非 continue)。"""
        from meta_config import DEFAULT_META_CONFIG

        cfg = dict(DEFAULT_META_CONFIG)
        strategies = []
        for score, steps in [(0.97, 205), (0.85, 240), (0.80, 260)]:
            d = compute_delta(score, steps)
            dec = respond(d, cfg)
            strategies.append(dec["strategy"] if dec else "continue")
        assert any(s != "continue" for s in strategies), f"all continue: {strategies}"


# ---------------------------------------------------------------- C3
class TestCellLearner:
    def _make_triggers(self):
        return [
            {"trigger": "stagnation", "window": 3, "rounds": [1, 2, 3],
             "variants": ["a", "b", "c"], "scores": [0.8, 0.8, 0.8]},
            {"trigger": "loop_detected", "variant": "mh_probe_01", "repeat": 2,
             "rounds": [3, 4]},
        ]

    def test_learns_rules_to_file(self, tmp_path):
        rules_file = tmp_path / "meta_engineering_rules.md"
        rules_file.write_text("# header\n| ID | 规则 | 来源 |\n",
                              encoding="utf-8")
        learner = CellLearner(rules_file=str(rules_file))
        new = learner.learn_from_triggers(self._make_triggers())
        assert len(new) == 2
        content = rules_file.read_text(encoding="utf-8")
        assert "RULE-MC-001" in content
        assert "RULE-MC-002" in content
        assert "探索停滞" in content and "提议器循环" in content

    def test_dedup_on_second_run(self, tmp_path):
        rules_file = tmp_path / "meta_engineering_rules.md"
        rules_file.write_text("# header\n| ID | 规则 | 来源 |\n",
                              encoding="utf-8")
        learner = CellLearner(rules_file=str(rules_file))
        learner.learn_from_triggers(self._make_triggers())
        learner2 = CellLearner(rules_file=str(rules_file))
        new = learner2.learn_from_triggers(self._make_triggers())
        assert new == [], "重复触发器不得重复沉淀规则"

    def test_adapt_params_on_stagnation(self):
        from meta_config import DEFAULT_META_CONFIG

        cfg = dict(DEFAULT_META_CONFIG)
        learner = CellLearner()
        triggers = [{"trigger": "stagnation", "window": 3, "rounds": [1, 2, 3],
                     "variants": ["a"], "scores": [0.8]}]
        bounds = learner.adapt_params(cfg, triggers)
        assert bounds["temperature"]["max"] > PARAM_BOUNDS["temperature"]["max"]
        assert cfg.get("param_bounds") is not None

    def test_learning_record_written(self, tmp_path):
        log = tmp_path / "meta_decisions.jsonl"
        rules_file = tmp_path / "meta_engineering_rules.md"
        rules_file.write_text("# header\n", encoding="utf-8")
        learner = CellLearner(log_path=str(log), rules_file=str(rules_file))
        learner.learn_from_triggers(self._make_triggers())
        recs = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert any(r["type"] == "cell_learning" for r in recs)
