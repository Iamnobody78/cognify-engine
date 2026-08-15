"""frontier — MH-3 Pareto 前沿维护（质量 vs 成本双目标）。

原则（斯坦福 Meta-Harness）:
  - 不被单一维度绑架: 候选按 (quality, cost) 双目标排序
  - Pareto 支配: A 支配 B ⇔ A.quality ≥ B.quality ∧ A.cost ≤ B.cost ∧ 至少一项严格
  - 前沿 = 不被任何其他候选支配的集合（左下凸包前沿）

约定:
  - quality ∈ [0, 1]（越大越好, 如胜率/通过率归一化）
  - cost ∈ [0, +∞)（越小越好, 如 token 消耗/运行时间/金钱）

组成:
  - dominates(a, b): 支配判定
  - ParetoFrontier: 插入/查询/前沿枚举
  - plot_ascii(): 终端可视化（ASCII 散点）
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    """候选的 (id, quality, cost) 三要素。"""
    id: str
    quality: float
    cost: float


def dominates(a: Point, b: Point) -> bool:
    """a 支配 b: quality 不低且 cost 不高，且至少一项严格。"""
    return (a.quality >= b.quality and a.cost <= b.cost and
            (a.quality > b.quality or a.cost < b.cost))


class ParetoFrontier:
    """增量维护的非支配集。"""

    def __init__(self):
        self._points: dict[str, Point] = {}

    def insert(self, point: Point) -> bool:
        """插入候选；若被现有支配则拒绝，返回 False。若加入则剔除
        所有被其支配的旧候选，返回 True。"""
        # 等 quality 等 cost 的重复 id 视为更新
        if point.id in self._points and self._points[point.id] == point:
            return False
        # 被支配 → 拒绝
        if any(dominates(p, point) for p in self._points.values()):
            return False
        # 剔除被支配者
        self._points = {pid: p for pid, p in self._points.items()
                        if not dominates(point, p)}
        self._points[point.id] = point
        return True

    def frontier(self) -> list[Point]:
        """返回非支配点（按 quality 降序，cost 升序）。"""
        pts = list(self._points.values())
        pts.sort(key=lambda p: (-p.quality, p.cost))
        return pts

    def is_dominated(self, point: Point) -> bool:
        return any(dominates(p, point) for p in self._points.values())

    def best(self, weight_quality: float = 0.5) -> Point | None:
        """按线性加权选最优: score = w*q + (1-w)*(1-normalized cost)。"""
        pts = self.frontier()
        if not pts:
            return None
        max_cost = max(p.cost for p in pts) or 1.0
        best_pt, best_s = None, -1.0
        for p in pts:
            s = (weight_quality * p.quality +
                 (1 - weight_quality) * (1 - p.cost / max_cost))
            if s > best_s:
                best_s, best_pt = s, p
        return best_pt

    def __len__(self) -> int:
        return len(self._points)

    def __contains__(self, pid: str) -> bool:
        return pid in self._points

    def plot_ascii(self, width: int = 40, height: int = 12) -> str:
        """ASCII 散点图: x=quality(0..1), y=1-cost_norm(0..1)。"""
        pts = self.frontier()
        if not pts:
            return "(空前沿)"
        max_cost = max(p.cost for p in pts) or 1.0
        grid = [[" " for _ in range(width)] for _ in range(height)]
        for p in pts:
            x = min(width - 1, int(p.quality * (width - 1)))
            y = min(height - 1, int((1 - p.cost / max_cost) * (height - 1)))
            grid[y][x] = "*"
        rows = []
        for y in range(height - 1, -1, -1):
            rows.append("|" + "".join(grid[y]) + "|")
        rows.append("+" + "-" * width + "+")
        return "\n".join(rows)
