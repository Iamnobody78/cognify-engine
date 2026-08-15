# -*- coding: utf-8 -*-
"""MH-3: Pareto frontier + evolution loop tests.

AC1: dominates 支配判定
AC2: ParetoFrontier 插入/剔除/前沿枚举
AC3: best 线性加权选择
AC4: ASCII 可视化
AC5: EvolutionLoop ≥3 轮 提议→评分→合并
AC6: 严格裁决门（被支配候选不合并）
AC7: 每轮轨迹落盘（反馈闭环）
"""

import pytest

from src.pareto import EvolutionLoop, ParetoFrontier, Point, dominates
from src.proposer import Candidate, CandidateWriter
from src.trace import TraceStore


# ---------- AC1/AC2/AC3/AC4: frontier ----------
class TestFrontier:
    def test_dominates(self):
        a = Point("a", 0.9, 10)
        b = Point("b", 0.8, 12)
        c = Point("c", 0.9, 12)
        assert dominates(a, b)
        assert not dominates(b, a)
        assert dominates(a, c)  # 同 quality 更低 cost → 支配
        assert not dominates(Point("d", 0.5, 5), Point("e", 0.5, 5))  # 相等

    def test_insert_keeps_non_dominated(self):
        f = ParetoFrontier()
        assert f.insert(Point("a", 0.9, 10))
        assert not f.insert(Point("b", 0.8, 12))      # 被 a 支配 → False
        assert f.insert(Point("c", 0.95, 8))          # 支配 a → True, 剔除 a
        ids = {p.id for p in f.frontier()}
        assert ids == {"c"}
        assert "a" not in f

    def test_frontier_sorted(self):
        f = ParetoFrontier()
        for pt in [Point("x1", 0.7, 5), Point("x2", 0.95, 20),
                   Point("x3", 0.85, 8)]:
            f.insert(pt)
        pts = f.frontier()
        assert [p.id for p in pts] == ["x2", "x3", "x1"]  # quality 降序

    def test_best_weighted(self):
        f = ParetoFrontier()
        f.insert(Point("hi_qual", 0.95, 50))
        f.insert(Point("cheap", 0.6, 2))
        assert f.best(weight_quality=0.9).id == "hi_qual"
        assert f.best(weight_quality=0.1).id == "cheap"

    def test_plot_ascii(self):
        f = ParetoFrontier()
        f.insert(Point("a", 0.9, 10))
        f.insert(Point("b", 0.5, 2))
        plot = f.plot_ascii()
        assert "*" in plot
        assert plot.startswith("|")

    def test_is_dominated(self):
        f = ParetoFrontier()
        f.insert(Point("a", 0.9, 10))
        assert f.is_dominated(Point("z", 0.8, 11))


# ---------- AC5/AC6/AC7: loop ----------
class TestLoop:
    def test_three_round_evolution(self, tmp_path):
        store = TraceStore(tmp_path)
        writer = CandidateWriter(tmp_path)
        loop = EvolutionLoop(store, root=tmp_path, max_rounds=3)

        def propose(idx, frontier):
            cand = writer.create(f"cand_{idx}")
            writer.write_source(cand, "v.py", f"VERSION={idx}\n")
            return cand

        def score(cand):
            q = 0.5 + 0.1 * int(cand.name.split("_")[1])
            c = 20 - int(cand.name.split("_")[1])
            return q, c

        result = loop.run(propose, score)
        assert len(result.rounds) == 3  # AC5: 至少 3 轮
        # 每轮评分单调改善 → 前沿保留全部
        assert result.rounds[0]["merged"] is True
        assert result.frontier is loop.frontier
        # AC7: 轨迹落盘
        metas = store.list_traces()
        assert len(metas) == 3
        assert all(m["status"] == "ok" for m in metas)

    def test_strict_gate_rejects_dominated(self, tmp_path):
        store = TraceStore(tmp_path)
        writer = CandidateWriter(tmp_path)
        loop = EvolutionLoop(store, root=tmp_path, max_rounds=3,
                             merge_policy="strict")
        seq = iter([(0.95, 10), (0.8, 15), (0.9, 12)])  # 后两轮被第一轮支配

        def propose(idx, frontier):
            return writer.create(f"cand_{idx}")

        def score(cand):
            return next(seq)

        result = loop.run(propose, score)
        assert len(result.merged) == 1  # AC6: 仅第一轮进入前沿
        assert result.merged[0].endswith("_cand_1")

    def test_propose_none_skipped(self, tmp_path):
        store = TraceStore(tmp_path)
        loop = EvolutionLoop(store, root=tmp_path, max_rounds=2)
        result = loop.run(lambda i, f: None, lambda c: (0, 0))
        assert len(result.rounds) == 2
        assert all(r["candidate"] is None for r in result.rounds)
        assert result.merged == []

    def test_score_exception_traced(self, tmp_path):
        store = TraceStore(tmp_path)
        writer = CandidateWriter(tmp_path)
        loop = EvolutionLoop(store, root=tmp_path, max_rounds=2)

        def propose(idx, frontier):
            return writer.create(f"cand_{idx}")

        def score(cand):
            raise RuntimeError("sim crash")

        result = loop.run(propose, score)
        assert all("评分异常" in r["reason"] for r in result.rounds)
        metas = store.list_traces()
        assert all(m["status"] == "failed" for m in metas)

    def test_best_after_loop(self, tmp_path):
        store = TraceStore(tmp_path)
        writer = CandidateWriter(tmp_path)
        loop = EvolutionLoop(store, root=tmp_path, max_rounds=3)
        seq = iter([(0.7, 30), (0.9, 15), (0.8, 5)])

        def propose(idx, frontier):
            return writer.create(f"cand_{idx}")

        def score(cand):
            return next(seq)

        result = loop.run(propose, score)
        # 前沿 = {(0.9,15), (0.8,5)}（(0.7,30) 被 (0.9,15) 支配剔除）
        best = result.frontier.best(weight_quality=1.0)   # 纯质量 → 0.9
        assert best.quality == 0.9
        best2 = result.frontier.best(weight_quality=0.0)  # 纯成本 → 0.8/5
        assert best2.quality == 0.8 and best2.cost == 5
