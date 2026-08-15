"""LiDAR → 仿真 obs 感知适配器骨架 (BS-DEPLOY-PREP A4) — 契约修正版。

状态: 🟦 设计骨架 — 未测试 (红线 #2: 禁止在未校准 LiDAR 的情况下依赖其数据)
待硬件就绪后: 接 YDLIDAR X4 驱动, 实测点云验证转换逻辑。

接口契约 (与 lightweight_env.py 严格对齐 — 2026-08-11 修正):
  9 维 obs = [edge_F, edge_B, edge_L, edge_R, opp_dist, opp_angle, speed,
              vel_fwd, vel_right]
  - edge_*:  归一化 0-1, **1.0=安全中心, 0.0=已跌出台** (与 env 同语义;
             修正前版本写成 "0=中心,1=危险" — 方向倒置, 会导致
             策略在台中央即触发跌落终止)
  - opp_dist: 0-4m (最近障碍物距离, 4.0 cap 与 env 一致)
  - opp_angle: -180..180° (对手方位, 相对机头)
  - speed:  -0.7..0.7 (当前速度, 归一化)
  - vel_fwd / vel_right: -1..1 对手速度在机体前向/右向轴的投影 (/0.6, clamp)
     (Sprint 37 T1 新增通道; Pico 无编码器, 该通道为骨架 — 由最近两帧
      极坐标差分估计, 无帧时 fail-open 回退 0.0)

修正记录 (2026-08-11, obs 契约审计):
  1. 维度 7 → 9 (补 vel_fwd/vel_right)
  2. edge 语义倒置修复 (env: 1.0=safe / 0.0=danger; 旧代码反向)
  3. 顺序 [L,R,F,B] → [F,B,L,R] (env 实际顺序)
  4. 无帧 fail-open 从全 0 改为 edge=1.0 (安全) + opp_dist=4.0 (无对手)
     — 与治理层 fail-open 哲学一致: 感知缺失 → 按安全默认处理
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

@dataclass
class LiDARPoint:
    """单帧扫描点 (极坐标 → 直角坐标预处理)。"""
    angle_deg: float
    distance_m: float
    quality: float = 1.0

@dataclass
class Obstacle:
    """点云聚类后的障碍物 (最近对手/水樽)。"""
    distance_m: float
    angle_deg: float
    width_m: float = 0.0

# 台板尺寸 (赛规: 75cm x 182cm, 圆角) — 用于边缘距离估算
RINK_HALF_LEN_M = 0.91   # 182cm / 2
RINK_HALF_WID_M = 0.375  # 75cm / 2
ROBOT_RADIUS_M = 0.075   # 与 lightweight_env 一致
# env 为圆形台 (DOHYO_RADIUS=0.40): LiDAR 墙距 → env edge 的镜像映射系数。
# 矩形台实测后需按象限标定 (GAP-7); 此系数仅为 env 语义镜像:
#   env.edge = 1.0 - 0.9 * (dist_from_center / 0.40)
#   而 LiDAR 墙距 w ≈ 0.40 - dist_from_center  ⇒  edge = 0.1 + 0.9 * (w / 0.40)
EDGE_REF_DIST_M = 0.40   # env DOHYO_RADIUS
EDGE_MIN_SAFE = 0.1      # env edge_front 在台中央的基准值
EDGE_RAMP = 0.9          # env 线性斜坡斜率 (1.0 - 0.9*ratio)

class LidarObsAdapter:
    """将 LiDAR 点云转换为 lightweight_env 兼容的 9 维 obs 向量。

    设计要点 (对齐 GAP-1/2/3/7/8):
      - 边缘: 检测连续地面距离突变 (胶纸缝隙/台板边缘) → 归一化
      - 对手/水樽: 点云中短距聚类最近点 → opp_dist + opp_angle
      - 免疫颜色/光照: 纯测距, 与赛规"当天公布颜色"天然解耦
    """

    def __init__(self, rink_half_len: float = RINK_HALF_LEN_M,
                 rink_half_wid: float = RINK_HALF_WID_M,
                 robot_radius: float = ROBOT_RADIUS_M):
        self.half_len = rink_half_len
        self.half_wid = rink_half_wid
        self.robot_r = robot_radius
        self.last_obs: Optional[List[float]] = None
        self.raw_frame: List[LiDARPoint] = field(default_factory=list)
        # 对手速度估计 (差分追踪): (dist_m, angle_deg, t)
        self._prev_opp: Optional[Tuple[float, float]] = None

    # -- 对外接口 -----------------------------------------------------

    def update_frame(self, points: List[LiDARPoint]) -> None:
        """注入一帧原始点云 (由驱动层回调)。"""
        self.raw_frame = points

    def to_obs(self, speed_normalized: float = 0.0, dt: float = 0.08) -> List[float]:
        """点云 → 9 维 obs。未收到帧时返回安全默认向量 (fail-open)。"""
        if not self.raw_frame:
            # fail-open: 感知缺失 → edge=1.0 (安全), opp_dist=4.0 (无对手)
            self.last_obs = [1.0, 1.0, 1.0, 1.0, 4.0, 0.0, speed_normalized, 0.0, 0.0]
            self._prev_opp = None
            return self.last_obs

        obstacles = self._cluster_nearest(self.raw_frame)
        edges = self._detect_edges(self.raw_frame)
        opp = self._nearest_obstacle(obstacles)

        opp_dist = opp.distance_m if opp else 4.0
        opp_angle = opp.angle_deg if opp else 0.0
        vel_fwd, vel_right = self._estimate_opp_vel(opp, dt)

        obs = [
            edges.get("front", 1.0),    # edge_F  (env 顺序: F,B,L,R)
            edges.get("back", 1.0),     # edge_B
            edges.get("left", 1.0),     # edge_L
            edges.get("right", 1.0),    # edge_R
            min(opp_dist, 4.0),         # opp_dist (4.0 cap, 同 env)
            opp_angle,                  # opp_angle
            max(-0.7, min(0.7, speed_normalized)),
            vel_fwd,                    # opp velocity → robot forward
            vel_right,                  # opp velocity → robot right
        ]
        self.last_obs = obs
        self._prev_opp = (opp_dist, opp_angle)
        return obs

    # -- 内部算法 (骨架, 待实测校准) -----------------------------------

    def _detect_edges(self, points: List[LiDARPoint]) -> dict:
        """边缘检测: 距离突变点 (台板边缘/胶纸缝隙) → 各向归一化边缘度。

        语义 (与 env 一致): 1.0=安全中心, 0.0=已到台缘/跌出。
        墙距 w → edge = 0.1 + 0.9 * clamp01(w / EDGE_REF_DIST_M)。
        """
        # 🟦 骨架: 按象限分组, 找 0.5-2.0m 区间的距离突变
        # 实测后需标定: 突变阈值 (预计 ±5cm), 象限权重
        sectors = {"left": [], "right": [], "front": [], "back": []}
        for p in points:
            a = p.angle_deg
            if -45 <= a < 45:
                sectors["front"].append(p.distance_m)
            elif 45 <= a < 135:
                sectors["right"].append(p.distance_m)
            elif -135 <= a < -45:
                sectors["left"].append(p.distance_m)
            else:
                sectors["back"].append(p.distance_m)
        edges = {}
        for name, dists in sectors.items():
            if not dists:
                edges[name] = 1.0  # 无数据 → 视为安全 (fail-open)
                continue
            nearest = min(dists)
            # env 镜像映射: 墙距近 → edge 低 (危险); 墙距远 → edge 高 (安全)
            ratio = max(0.0, min(1.0, nearest / EDGE_REF_DIST_M))
            edges[name] = EDGE_MIN_SAFE + EDGE_RAMP * ratio
        return edges

    def _cluster_nearest(self, points: List[LiDARPoint]) -> List[Obstacle]:
        """🟦 骨架: 简化聚类 — 直接取全量最近点 (单目标场景够用)。"""
        if not points:
            return []
        nearest = min(points, key=lambda p: p.distance_m)
        return [Obstacle(distance_m=nearest.distance_m,
                         angle_deg=nearest.angle_deg)]

    @staticmethod
    def _nearest_obstacle(obstacles: List[Obstacle]) -> Optional[Obstacle]:
        return min(obstacles, key=lambda o: o.distance_m) if obstacles else None

    def _estimate_opp_vel(self, opp: Optional[Obstacle],
                          dt: float) -> Tuple[float, float]:
        """🟦 骨架: 由最近两帧 opp 极坐标差分估计对手速度 (需实测标定)。

        Pico 无编码器: 该通道为可选增强; 无上一帧/无对手时回退 0.0 (fail-open)。
        机体坐标系: x=前向, y=右向 (与 env vel_fwd/vel_right 投影轴一致)。
        """
        if opp is None or self._prev_opp is None or dt <= 0.0:
            return 0.0, 0.0
        prev_dist, prev_angle = self._prev_opp
        # 相对机体笛卡尔 (右向为正, 与 env vel_right 一致)
        x_now = opp.distance_m * math.cos(math.radians(opp.angle_deg))
        y_now = -opp.distance_m * math.sin(math.radians(opp.angle_deg))
        x_prev = prev_dist * math.cos(math.radians(prev_angle))
        y_prev = -prev_dist * math.sin(math.radians(prev_angle))
        vel_fwd = (x_now - x_prev) / dt / 0.6
        vel_right = (y_now - y_prev) / dt / 0.6
        return max(-1.0, min(1.0, vel_fwd)), max(-1.0, min(1.0, vel_right))

# ── 自检 (仅验证契约形状, 非硬件测试) ───────────────────────────────
if __name__ == "__main__":
    import random

    adapter = LidarObsAdapter()
    # 模拟两帧: 前方 0.3m 有对手, 其余 0.6-0.9m 台板内 (安全)
    def make_frame(opp_d: float, opp_a: float) -> List[LiDARPoint]:
        pts = [LiDARPoint(angle_deg=a, distance_m=random.uniform(0.6, 0.9))
               for a in range(-180, 180, 5)]
        pts.append(LiDARPoint(angle_deg=opp_a, distance_m=opp_d))
        return pts

    adapter.update_frame(make_frame(0.3, 0.0))
    obs = adapter.to_obs()
    assert len(obs) == 9, f"obs 维度错误: {len(obs)} (期望 9)"
    assert abs(obs[4] - 0.3) < 1e-6, f"opp_dist 应取最近障碍物 0.3m, got {obs[4]}"
    assert obs[0] > 0.5, f"edge_F 语义: 0.3m 墙距应偏安全 (>0.5), got {obs[0]:.3f}"
    assert 0.0 <= obs[0] <= 1.0 and 0.0 <= obs[8] <= 1.0, "obs 越界"

    # fail-open: 空帧 → 全安全 + 无对手
    adapter.update_frame([])
    obs_fail = adapter.to_obs()
    assert obs_fail[:4] == [1.0, 1.0, 1.0, 1.0], "空帧应 fail-open 为安全边缘"
    assert obs_fail[4] == 4.0 and obs_fail[7] == 0.0 and obs_fail[8] == 0.0

    print(f"[OK] 9 维 obs: {[round(o, 3) for o in obs]}")
    print("[OK] 契约验证通过 (形状/语义/fail-open) — 硬件校准后需实测")
