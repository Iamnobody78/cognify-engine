"""src.pareto — MH-3 Pareto 前沿（质量 vs 成本）+ 提议→评分→合并循环。

原则（斯坦福 Meta-Harness）:
  - 帕累托思维: 不被单一维度绑架，双目标 (quality, cost) 前沿
  - 严格裁决门: 新候选 3 轮内优于当前最优才允许合并主分支
  - 完整反馈: 每轮写入 trace，下一轮提议者以历史为变异输入

组成:
  frontier.ParetoFrontier  非支配集维护（insert/frontier/best/plot_ascii）
  loop.EvolutionLoop        提议→评分→合并迭代（≥3 轮, strict/any 合并策略）
"""

from .frontier import ParetoFrontier, Point, dominates
from .loop import EvolutionLoop, LoopResult

MH3_VERSION = "1.0.0"

__all__ = ["ParetoFrontier", "Point", "dominates", "EvolutionLoop",
           "LoopResult", "MH3_VERSION"]
