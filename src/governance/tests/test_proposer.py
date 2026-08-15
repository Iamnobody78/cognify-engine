# -*- coding: utf-8 -*-
"""MH-2: proposer tests — 轨迹阅读器 + 候选写入器（文件系统变异算子）。

AC1: TraceReader 读取/检索/搜索完整轨迹
AC2: grep 式正则检索
AC3: cat 式全文展开（LLM 可消费）
AC4: 10M token 反馈预算统计
AC5: CandidateWriter 创建完整候选（src/ 文件树 + candidate.json）
AC6: 血缘（parent_trace_id）与轨迹产物导入
AC7: 整树复制与幂等
"""

import json
from pathlib import Path

import pytest

from src.proposer import Candidate, CandidateWriter, TraceReader
from src.trace import TraceStore, capture


@pytest.fixture()
def store(tmp_path):
    return TraceStore(tmp_path)


@pytest.fixture()
def reader(store):
    return TraceReader(store=store)


@pytest.fixture()
def writer(tmp_path):
    return CandidateWriter(tmp_path)


@pytest.fixture()
def seeded_store(store):
    """预置 3 条轨迹（含失败样本，供检索）。"""
    with capture(store, "run_v11") as t:
        t.step("sensor", detail="codegen drift detected")
        t.step("deploy", detail="deployed ok")
        t.artifact("policies.yaml", "rules: []")
    ok_id = t.trace_id
    with capture(store, "run_v12") as t2:
        t2.step("sensor", detail="no drift")
        t2.step("deploy", detail="commit 43aec94")
    try:
        with capture(store, "boom_run") as t3:
            t3.step("sensor", detail="crash in evaluator")
            raise RuntimeError("eval crash")
    except RuntimeError:
        pass  # 预期异常，轨迹已标记 failed
    return store, ok_id


# ---------- AC1/AC2/AC3/AC4: reader ----------
class TestReader:
    def test_read_and_list(self, seeded_store):
        store, ok_id = seeded_store
        reader = TraceReader(store=store)
        trace = reader.read_trace(ok_id)
        assert trace.name == "run_v11"
        metas = reader.list_traces()
        assert len(metas) == 3

    def test_search_by_name_and_step(self, seeded_store):
        store, _ = seeded_store
        reader = TraceReader(store=store)
        assert len(reader.search_traces("run_v11")) == 1
        assert len(reader.search_traces("deployed")) == 1  # 仅 run_v11 步骤文本
        assert len(reader.search_traces("nonexistent")) == 0

    def test_grep_regex(self, seeded_store):
        store, _ = seeded_store
        reader = TraceReader(store=store)
        hits = reader.grep_traces(r"crash")
        assert len(hits) == 1  # 仅 boom_run
        assert hits[0]["name"] == "boom_run"
        hits2 = reader.grep_traces(r"drift|crash")
        assert len(hits2) == 3  # run_v11 + run_v12("no drift") + boom_run

    def test_grep_invalid_regex_raises(self, reader):
        with pytest.raises(ValueError):
            reader.grep_traces("(")

    def test_cat_trace_human_readable(self, seeded_store):
        store, ok_id = seeded_store
        reader = TraceReader(store=store)
        text = reader.cat_trace(ok_id)
        assert "# trace" in text
        assert "run_v11" in text
        assert "[001] sensor" in text
        assert "[art] artifacts/policies.yaml" in text

    def test_cat_truncates(self, seeded_store):
        store, ok_id = seeded_store
        reader = TraceReader(store=store)
        short = reader.cat_trace(ok_id, max_chars=30)
        assert "truncated" in short

    def test_feedback_budget(self, seeded_store):
        store, _ = seeded_store
        reader = TraceReader(store=store)
        fb = reader.feedback_budget(max_tokens=10_000)
        assert fb["trace_count"] == 3
        assert fb["total_tokens"] > 0
        assert fb["used_pct"] > 0 and fb["used_pct"] <= 100


# ---------- AC5/AC6/AC7: writer ----------
class TestWriter:
    def test_create_candidate_with_source(self, writer):
        cand = writer.create("harness_a", parent_trace_id="trace1",
                             mutation_note="调整阈值 0.7→0.8")
        writer.write_source(cand, "scheduler.py", "def run():\n    pass\n")
        writer.write_source(cand, "sub/env.py", "ENV='test'\n")
        writer.finalize(cand)
        assert cand.file_count == 2
        src = writer.candidates_dir / cand.candidate_id / "src"
        assert (src / "scheduler.py").exists()
        assert (src / "sub" / "env.py").exists()
        meta_path = writer.candidates_dir / cand.candidate_id / "candidate.json"
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        assert data["parent_trace_id"] == "trace1"
        assert data["mutation_note"] == "调整阈值 0.7→0.8"

    def test_import_trace_artifacts(self, seeded_store, writer):
        store, ok_id = seeded_store
        cand = writer.create("seed_cand")
        n = writer.import_trace_artifacts(cand, ok_id, store)
        assert n == 1  # policies.yaml
        path = writer.candidates_dir / cand.candidate_id / "src" / "policies.yaml"
        assert path.exists()

    def test_import_missing_trace_returns_zero(self, writer):
        cand = writer.create("orphan")
        assert writer.import_trace_artifacts(cand, "no-such-trace",
                                             TraceStore(".")) == 0

    def test_write_tree_copies_whole_dir(self, writer, tmp_path):
        tree = tmp_path / "tree"
        (tree / "a" / "b").mkdir(parents=True)
        (tree / "main.py").write_text("print(1)", encoding="utf-8")
        (tree / "a" / "b" / "x.yaml").write_text("x: 1", encoding="utf-8")
        cand = writer.create("tree_cand")
        n = writer.write_tree(cand, tree)
        assert n == 2
        assert (writer.candidates_dir / cand.candidate_id / "src" / "a" / "b"
                / "x.yaml").exists()

    def test_load_and_list(self, writer):
        cand = writer.create("load_cand")
        writer.write_source(cand, "f.py", "pass\n")
        writer.finalize(cand)
        loaded = writer.load(cand.candidate_id)
        assert loaded.name == "load_cand"
        metas = writer.list_candidates()
        assert len(metas) == 1
        assert metas[0]["candidate_id"] == cand.candidate_id

    def test_set_metrics(self, writer):
        cand = writer.create("metric_cand")
        writer.set_metrics(cand, {"quality": 0.9, "cost": 12})
        loaded = writer.load(cand.candidate_id)
        assert loaded.metrics["quality"] == 0.9
        assert loaded.metrics["cost"] == 12

    def test_load_unknown_raises(self, writer):
        with pytest.raises(KeyError):
            writer.load("nope")
