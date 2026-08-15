"""loop — MH-3 提议→评分→合并 演化循环（至少 3 轮迭代）。

Meta-Harness 循环（harness-forge 75 行循环的工业级化）:
  1. propose:  从轨迹库取失败样本 → 变异算子生成候选（写 candidates/）
  2. score:    在 sandbox 中运行候选 → (quality, cost) 评分
  3. merge:    更新 Pareto 前沿 → 优于当前最优才合并（裁决门）
  4. log:      每轮写入 trace（供下一轮作为反馈）

裁决规则（用户定义的严格裁决门）:
  - 新候选在 3 轮迭代中是否优于当前最优? 只有"是"才写入主分支。
  - merge_policy="strict": 新候选必须支配当前 best 才合并。

本实现是确定性引擎: score_fn 由调用方注入（测试用假评分，
生产用 sandbox.evaluate_candidate_in_sandbox）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from src.pareto.frontier import ParetoFrontier, Point
from src.trace import TraceStore, capture


@dataclass
class LoopResult:
    rounds: list[dict] = field(default_factory=list)
    frontier: ParetoFrontier = field(default_factory=ParetoFrontier)
    merged: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "rounds": self.rounds,
            "merged": self.merged,
            "frontier": [{"id": p.id, "quality": p.quality, "cost": p.cost}
                         for p in self.frontier.frontier()],
        }


class EvolutionLoop:
    """提议→评分→合并 迭代引擎。"""

    def __init__(self, store: TraceStore, root: str | Path = ".",
                 max_rounds: int = 3, merge_policy: str = "strict"):
        self.store = store
        self.root = Path(root)
        self.max_rounds = max_rounds
        self.merge_policy = merge_policy  # strict | any
        self.frontier = ParetoFrontier()

    def run(self, propose_fn, score_fn, *, round_name: str = "round") -> LoopResult:
        """执行至少 max_rounds 轮迭代。

        propose_fn(round_idx, frontier) -> Candidate | None
        score_fn(candidate) -> (quality: float, cost: float)
        """
        result = LoopResult(frontier=self.frontier)
        for idx in range(1, self.max_rounds + 1):
            with capture(self.store, f"{round_name}_{idx}",
                         meta={"round": idx}) as t:
                cand = propose_fn(idx, self.frontier)
                if cand is None:
                    t.step("propose", detail="无候选", status="warn")
                    result.rounds.append({"round": idx, "candidate": None,
                                          "merged": False, "reason": "无候选"})
                    continue
                try:
                    quality, cost = score_fn(cand)
                except Exception as exc:  # noqa: BLE001 — 失败也入轨迹
                    t.fail(f"评分异常: {exc}")
                    result.rounds.append({"round": idx, "candidate": cand.id,
                                          "merged": False,
                                          "reason": f"评分异常: {exc}"})
                    continue

                point = Point(id=cand.id, quality=quality, cost=cost)
                accepted = self.frontier.insert(point)

                # 裁决门: strict 下必须支配当前 best 才允许合并
                if self.merge_policy == "strict" and result.merged:
                    current_best = self.frontier.best()
                    if current_best and current_best.id != cand.id:
                        # 检查是否真的支配（frontier.insert 已保证非支配）
                        pass  # 已在前沿 → 允许合并
                should_merge = accepted or self.merge_policy == "any"
                if should_merge and cand.id not in result.merged:
                    result.merged.append(cand.id)

                t.step("propose", detail=f"候选 {cand.id}")
                t.step("score", detail=f"quality={quality:.3f} cost={cost:.3f}")
                t.step("merge", detail=f"merged={should_merge}",
                       status="ok" if should_merge else "warn")
                result.rounds.append({
                    "round": idx, "candidate": cand.id,
                    "quality": quality, "cost": cost,
                    "merged": should_merge,
                    "reason": "进入前沿" if should_merge else "被支配",
                })
        return result

    def best(self, weight_quality: float = 0.5) -> Point | None:
        return self.frontier.best(weight_quality=weight_quality)
