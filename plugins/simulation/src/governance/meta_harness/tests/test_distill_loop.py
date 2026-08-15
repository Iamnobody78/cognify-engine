# -*- coding: utf-8 -*-
"""
test_distill_loop.py — Sprint 21 P2 M1(数据管道)+M3(扰动先验) 回归测试
========================================================================
PM 裁决: M1+M3 优先 (数据基础设施, 成本低收益明确); M2 评估层重构延后。
防 decoding collapse: 蒸馏结构化字段 (verdict/reason/layer), 不走 LLM 自由文本。
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import distill_loop
import code_agent_proposer


# ---------------------------------------------------------------- 1. 数据管道基础
def _dg(ts, vid, layer, verdict, score=1.0, reason="r"):
    return {"type": "diff_gate", "ts": ts, "variant_id": vid, "layer": layer,
            "score": score, "steps": 200, "diff_verdict": verdict,
            "diff_blocked": True, "reason": reason}


def test_load_jsonl_skips_bad_lines(tmp_path):
    p = tmp_path / "d.jsonl"
    p.write_text('{"a": 1}\n\nnot-json\n{"b": 2}\n', encoding="utf-8")
    recs = distill_loop.load_jsonl(str(p))
    assert len(recs) == 2


def test_filter_diff_gate_all():
    recs = [_dg("t1", "v1", "physics", "SUSPICIOUS"),
            {"type": "monitoring_report", "ts": "t2"},
            _dg("t3", "v2", "mapping", "INCONCLUSIVE")]
    dg = distill_loop.filter_diff_gate(recs)
    assert len(dg) == 2


def test_filter_diff_gate_verdict_whitelist():
    recs = [_dg("t1", "v1", "physics", "SUSPICIOUS"),
            _dg("t3", "v2", "mapping", "INCONCLUSIVE")]
    dg = distill_loop.filter_diff_gate(recs, verdicts=["SUSPICIOUS"])
    assert len(dg) == 1 and dg[0]["diff_verdict"] == "SUSPICIOUS"


# ---------------------------------------------------------------- 2. D1 失敏检测
def test_distill_d1_saturated_suspicious():
    recs = [_dg("t1", "v1", "physics", "SUSPICIOUS", score=1.0)]
    rules, stats = distill_loop.distill_d1(recs)
    assert stats["count"] == 1 and stats["saturated"] == 1
    assert rules[0]["id"] == "D1-v1"
    assert "饱和" in rules[0]["signal"]
    assert "次级信号" in rules[0]["action"]


def test_distill_d1_non_saturated():
    recs = [_dg("t1", "v1", "mapping", "SUSPICIOUS", score=0.8)]
    rules, stats = distill_loop.distill_d1(recs)
    assert stats["saturated"] == 0
    assert "饱和" not in rules[0]["signal"]
    assert "人工审查" in rules[0]["action"]


def test_distill_d1_ignores_inconclusive():
    recs = [_dg("t1", "v1", "rules", "INCONCLUSIVE")]
    rules, stats = distill_loop.distill_d1(recs)
    assert rules == [] and stats["count"] == 0


def test_distill_d1_by_layer_stats():
    recs = [_dg("t1", "v1", "physics", "SUSPICIOUS"),
            _dg("t2", "v2", "mapping", "SUSPICIOUS")]
    _, stats = distill_loop.distill_d1(recs)
    assert stats["by_layer"] == {"physics": 1, "mapping": 1}


# ---------------------------------------------------------------- 3. D2 扰动先验
def test_distill_d2_inconclusive_prior():
    recs = [_dg("t1", "v1", "mapping", "INCONCLUSIVE")]
    rules, stats = distill_loop.distill_d2(recs)
    assert stats["count"] == 1
    r = rules[0]
    assert r["layer"] == "mapping"
    assert r["min_change"] == ">=20%"
    assert "先验" in r["action"]


def test_distill_d2_unknown_layer_generic():
    recs = [_dg("t1", "v1", "reward", "INCONCLUSIVE")]
    rules, _ = distill_loop.distill_d2(recs)
    assert rules[0]["min_change"] == "未知"
    assert "通用" in rules[0]["action"]


def test_distill_d2_ignores_suspicious():
    recs = [_dg("t1", "v1", "physics", "SUSPICIOUS")]
    rules, stats = distill_loop.distill_d2(recs)
    assert rules == [] and stats["count"] == 0


# ---------------------------------------------------------------- 4. D3 多样性
def test_distill_d3_matrix():
    recs = [_dg("t1", "v1", "physics", "SUSPICIOUS"),
            _dg("t2", "v2", "mapping", "INCONCLUSIVE"),
            _dg("t3", "v3", "physics", "SUSPICIOUS")]
    s = distill_loop.distill_d3(recs)
    assert s["total_blocked"] == 3
    assert s["by_verdict"] == {"SUSPICIOUS": 2, "INCONCLUSIVE": 1}
    assert s["layer_x_verdict"]["physics"]["SUSPICIOUS"] == 2


def test_distill_d3_mcp_dist():
    mcp = [{"tool": "hypothesis_stats"}, {"tool": "meta_config_status"},
           {"tool": "hypothesis_stats"}]
    s = distill_loop.distill_d3([], mcp)
    assert s["mcp_tools"]["hypothesis_stats"] == 2


# ---------------------------------------------------------------- 5. 输出与端到端
def test_write_rules_versioned(tmp_path):
    rules = {"meta": {"sprint": "S21"}, "d1": []}
    path = distill_loop.write_rules(rules, str(tmp_path), ts="20260808_000000")
    assert os.path.basename(path) == "distill_rules_20260808_000000.json"
    with open(path, encoding="utf-8") as f:
        assert json.load(f)["meta"]["sprint"] == "S21"


def test_run_end_to_end(tmp_path):
    d = tmp_path / "decisions.jsonl"
    d.write_text("\n".join([
        json.dumps(_dg("20260808_100000", "v1", "physics", "SUSPICIOUS")),
        json.dumps(_dg("20260808_100001", "v2", "mapping", "INCONCLUSIVE")),
        json.dumps({"type": "monitoring_report", "ts": "20260808_100002"}),
    ]), encoding="utf-8")
    m = tmp_path / "mcp.jsonl"
    m.write_text(json.dumps({"tool": "hypothesis_stats"}) + "\n", encoding="utf-8")
    out = tmp_path / "exp"
    s = distill_loop.run(str(d), str(m), str(out))
    assert s["diff_gate_total"] == 2
    assert s["suspicious"] == 1 and s["inconclusive"] == 1
    assert os.path.exists(s["rules_file"])
    with open(s["rules_file"], encoding="utf-8") as f:
        doc = json.load(f)
    assert doc["d2_perturbation_prior"][0]["layer"] == "mapping"
    assert doc["d3_diversity"]["mcp_tools"]["hypothesis_stats"] == 1


def test_run_since_filter(tmp_path):
    d = tmp_path / "d.jsonl"
    d.write_text("\n".join([
        json.dumps(_dg("20260807_100000", "v1", "physics", "SUSPICIOUS")),
        json.dumps(_dg("20260808_100000", "v2", "mapping", "INCONCLUSIVE")),
    ]), encoding="utf-8")
    m = tmp_path / "m.jsonl"
    m.write_text("", encoding="utf-8")
    s = distill_loop.run(str(d), str(m), str(tmp_path / "exp"), since="20260808")
    assert s["diff_gate_total"] == 1 and s["inconclusive"] == 1


# ---------------------------------------------------------------- 6. M3 扰动先验
def _hist():
    return {"candidates": [], "pareto": [], "defects": [], "gate": {},
            "hypothesis_hits": {"confirmed": 0, "rejected": 0}}


def test_m3_prior_in_system_prompt():
    prompt = code_agent_proposer.build_system_prompt(_hist())
    assert "行为感知阈值" in prompt
    assert ">= 10 度" in prompt and ">= 20%" in prompt and ">= 0.2" in prompt
    assert "INCONCLUSIVE" in prompt


def test_m3_prior_const_definition():
    p = code_agent_proposer.PERTURBATION_PRIOR
    assert "角度锚点" in p and "数值阈值" in p and "物理系数" in p


def test_m3_prior_not_breaking_basic_prompt():
    prompt = code_agent_proposer.build_system_prompt(_hist())
    assert "硬约束" in prompt
    assert "输出严格 JSON" in prompt
    assert "anchor" in prompt
