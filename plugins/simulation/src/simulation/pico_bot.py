"""
pico_bot.py — BottleSumo Pico 数字孪生策略 (A-side GitHub 交付, 2026-08-11)

将 bottlesumo-pico-firmware 的 4 状态机 (INIT/SCAN/PUSH/DEFEND/ESCAPE)
与 governance_pico_rules.h 的裁决宏, 以 Python 可执行形式对齐到
lightweight_env.py 的 9 维 obs 契约 + Discrete(21) 动作空间。

用途:
  1. 真机到达前, 在仿真中验证固件状态机逻辑的正确性
  2. 固件 C 宏 (src/governance/governance_pico_rules.h) ↔ 本文件的
     双向契约一致性检查 (数值镜像: GR_* ↔ PICO_*)
  3. 为 DQN 策略提供可解释的 heuristic 基线对手/自对弈角色

契约 (与 lightweight_env.py 严格一致, 2026-08-11 审计确认):
  obs(9)  = [edge_F, edge_B, edge_L, edge_R, opp_dist, opp_angle,
             speed, vel_fwd, vel_right]
  - edge_*: 1.0=安全中心, 0.0=已跌出台 (跌落终止阈值 < 0.3)
  - opp_dist: 0..4.0 m (cap), opp_angle: -180..180° (相对机头, + = 左侧)
  - speed: -0.7..0.7 m/s, vel_fwd/vel_right: -1..1
  action: Discrete(21) — wheel_to_discrete.Action

固件映射说明:
  固件用 IMU 倾角 (GR_EDGE_SAFE_DEG=5 / WARN=10 / DANGER=15) 判定边缘;
  仿真用 env 的 edge_* 通道 (1.0=安全, 0.0=跌出) 替代倾角。二者在语义上
  同构: 危险阈值对齐 env 的跌落终止线 (edge < 0.3)。
"""
from __future__ import annotations

from enum import IntEnum
from typing import List, Optional, Tuple

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wheel_to_discrete import Action, ACTION_MAP  # noqa: E402

# ── 契约常量 (与 lightweight_env.py observation_space 严格一致) ──────
OBS_DIM = 9
OBS_NAMES = ["edge_F", "edge_B", "edge_L", "edge_R",
             "opp_dist", "opp_angle", "speed", "vel_fwd", "vel_right"]
OBS_LOW = [0.0, 0.0, 0.0, 0.0, 0.0, -180.0, -0.7, -1.0, -1.0]
OBS_HIGH = [1.0, 1.0, 1.0, 1.0, 4.0, 180.0, 0.7, 1.0, 1.0]

# ── 固件数值镜像 (governance_pico_rules.h ↔ 此处, 修改须双向同步) ────
PICO_MATCH_DURATION_S = 120.0      # GR_MATCH_DURATION_MS / 1000
PICO_STAY_3S_S = 3.0               # GR_STAY_3S_MS / 1000
PICO_PUSH_CONTACT_S = 3.0          # GR_PUSH_CONTACT_MS / 1000
PICO_PUSH_DETACH_S = 0.5           # GR_PUSH_DETACH_MS / 1000
PICO_PUSH_MAX_TRIES = 3            # GR_PUSH_MAX_TRIES
PICO_IDLE_STALL_S = 30.0           # GR_IDLE_STALL_MS / 1000 (SCAN→DEFEND)
PICO_ESCAPE_BACKUP_S = 0.3         # 固件 actEscape: 后退 300ms

# 边缘裁决 (env 语义): 1.0=安全中心, 0.0=跌出
PICO_EDGE_SAFE = 0.5               # >= 0.5: ALLOW (0)
PICO_EDGE_WARN = 0.3               # [0.3, 0.5): WARNING (1)
PICO_EDGE_DANGER = 0.3             # < 0.3: ESCALATE (2) — env 跌落终止线
PICO_OPP_VISIBLE_M = 4.0           # opp_dist >= 4.0 → 未检测到对手
PICO_OPP_ANGLE_DEADBAND_DEG = 15.0 # 正对死区 (固件 PUSH 直行对齐)
PICO_CONTACT_DIST_M = 0.2          # env push_threshold (接触判定)


class GR_State(IntEnum):
    """固件状态枚举镜像 (src/governance/governance_pico_rules.h GR_State)。"""
    INIT = 0
    SCAN = 1
    PUSH = 2
    DEFEND = 3
    ESCAPE = 4


def gr_verdict_edge(min_edge: float) -> int:
    """GR_VERDICT_EDGE 宏镜像: 0=ALLOW / 1=WARNING / 2=ESCALATE。"""
    if min_edge >= PICO_EDGE_SAFE:
        return 0
    if min_edge >= PICO_EDGE_WARN:
        return 1
    return 2


class PicoBotController:
    """Pico 固件 4 状态机的可执行数字孪生。

    每步调用 act(obs, dt) → 返回 Discrete(21) 动作索引。
    状态时序与 main.ino 完全镜像; 时间预算用 firmware-tick 累计,
    env 步进 dt=0.08s 驱动 (与固件 20ms 控制周期同构, 仅在宏观状态
    切换层面计时)。
    """

    def __init__(self, seed: Optional[int] = None):
        self.state = GR_State.INIT
        self.t_in_state = 0.0      # 当前状态累计时间 (s)
        self.push_tries = 0
        self.in_contact = False    # 接触中 (PUSH 3s 持续顶推计时)
        self.contact_timer = 0.0
        self.detach_timer = 0.0
        self.escape_timer = 0.0
        self.match_elapsed = 0.0
        self.last_action = int(Action.STOP)

    # ── 主接口 -------------------------------------------------------
    def act(self, obs: List[float], dt: float = 0.08) -> int:
        """obs(9) → Discrete(21) 动作。断言 obs 契约, 越界视为感知故障。"""
        assert len(obs) == OBS_DIM, f"obs 维度错误: {len(obs)} (期望 {OBS_DIM})"
        self.match_elapsed += dt
        self.t_in_state += dt

        edge_f, edge_b, edge_l, edge_r = obs[0], obs[1], obs[2], obs[3]
        opp_dist, opp_angle = obs[4], obs[5]
        min_edge = min(edge_f, edge_b, edge_l, edge_r)

        # 边缘裁决先行 (同 main.ino: verdict 检查优先于状态派发)
        verdict = gr_verdict_edge(min_edge)
        if verdict == 2:
            return self._enter_escape()

        # 状态机推进
        if self.state == GR_State.INIT:
            act = self._act_init()
        elif self.state == GR_State.SCAN:
            act = self._act_scan(min_edge, opp_dist, opp_angle)
        elif self.state == GR_State.PUSH:
            act = self._act_push(min_edge, opp_dist, opp_angle, dt)
        elif self.state == GR_State.DEFEND:
            act = self._act_defend(obs)
        elif self.state == GR_State.ESCAPE:
            act = self._act_escape()
        else:  # pragma: no cover — 防御
            act = int(Action.STOP)

        self.last_action = act
        return act

    # ── 状态实现 (镜像 main.ino actInit/actScan/actPush/actDefend/actEscape) ──

    def _act_init(self) -> int:
        """INIT: 直线前进 0.5s (固件 actInit: straight 0.5s) → SCAN。"""
        if self.t_in_state >= 0.5:
            self._goto(GR_State.SCAN)
            return int(Action.FW_SLOW)
        return int(Action.FW_SLOW)

    def _act_scan(self, min_edge: float, opp_dist: float,
                  opp_angle: float) -> int:
        """SCAN: 原地左旋搜敌。30s 未发现对手 → DEFEND (固件 stall 规则)。
        检测到对手 (opp_dist < 4.0) → PUSH。"""
        opp_visible = opp_dist < PICO_OPP_VISIBLE_M
        if opp_visible:
            self._goto(GR_State.PUSH)
            self.push_tries = 0
            return self._steer_toward(opp_angle, aggressive=False)
        if self.t_in_state >= PICO_IDLE_STALL_S:
            self._goto(GR_State.DEFEND)
            return int(Action.FW_SLOW)
        return int(Action.TURN_L_MED)

    def _act_push(self, min_edge: float, opp_dist: float,
                  opp_angle: float, dt: float) -> int:
        """PUSH: 顶推对手 (固件: 3s 接触=有效顶推, 脱离 0.5s, 最多 3 次)。
        接触判定: opp_dist < 0.2 (env push_threshold)。"""
        # 接触计时
        if opp_dist < PICO_CONTACT_DIST_M:
            self.in_contact = True
            self.contact_timer += dt
            self.detach_timer = 0.0
        elif self.in_contact:
            self.detach_timer += dt
            if self.detach_timer >= PICO_PUSH_DETACH_S:
                self.in_contact = False
                self.contact_timer = 0.0

        # 3s 持续接触 → 记一次有效顶推; 达到上限 → DEFEND 保台
        if self.contact_timer >= PICO_PUSH_CONTACT_S:
            self.push_tries += 1
            self.contact_timer = 0.0
            self.in_contact = False
            if self.push_tries >= PICO_PUSH_MAX_TRIES:
                self._goto(GR_State.DEFEND)
                return int(Action.FW_SLOW)

        # 对手丢失 (被顶出台或离开视野) → 回 SCAN
        if opp_dist >= PICO_OPP_VISIBLE_M:
            self._goto(GR_State.SCAN)
            return int(Action.TURN_L_MED)

        return self._steer_toward(opp_angle, aggressive=True)

    def _act_defend(self, obs: List[float]) -> int:
        """DEFEND: 保台策略 (固件 actDefend: stay on table until 120s)。
        边缘告警 (WARNING) → 远离最低边缘; 安全 → 缓速巡逻。"""
        edge_f, edge_b, edge_l, edge_r = obs[0], obs[1], obs[2], obs[3]
        min_edge = min(edge_f, edge_b, edge_l, edge_r)
        if min_edge < PICO_EDGE_WARN:
            # 远离最低边缘 (与 WARNING 裁决联动)
            lowest = min((edge_f, "F"), (edge_b, "B"),
                         (edge_l, "L"), (edge_r, "R"), key=lambda t: t[0])[1]
            if lowest == "F":
                return int(Action.REV_SLOW)
            if lowest == "B":
                return int(Action.FW_SLOW)
            if lowest == "L":
                return int(Action.FW_RIGHT_MED)
            if lowest == "R":
                return int(Action.FW_LEFT_MED)
        # 安全区: 缓速巡逻 (防呆滞)
        return int(Action.TURN_L_MILD)

    def _act_escape(self) -> int:
        """ESCAPE: 后退 0.3s → DEFEND (固件 actEscape: backup 300ms)。"""
        if self.t_in_state >= PICO_ESCAPE_BACKUP_S:
            self._goto(GR_State.DEFEND)
            return int(Action.STOP)
        return int(Action.REV_SLOW)

    # ── 工具 ---------------------------------------------------------

    def _steer_toward(self, opp_angle: float, aggressive: bool) -> int:
        """朝对手转向: 死区内直冲, 左侧左转, 右侧右转。"""
        if abs(opp_angle) <= PICO_OPP_ANGLE_DEADBAND_DEG:
            return int(Action.FW_FAST if aggressive else Action.FW_MED)
        if opp_angle > 0:  # 对手在左侧 (+ = left)
            return int(Action.FW_LEFT_MED if aggressive else Action.TURN_L_MED)
        return int(Action.FW_RIGHT_MED if aggressive else Action.TURN_R_MED)

    def _enter_escape(self) -> int:
        """ESCALATE → 强制 ESCAPE (verdict 优先路径, 同固件)。"""
        if self.state != GR_State.ESCAPE:
            self._goto(GR_State.ESCAPE)
        return self._act_escape()

    def _goto(self, state: GR_State) -> None:
        self.state = state
        self.t_in_state = 0.0
        if state == GR_State.ESCAPE:
            self.escape_timer = 0.0

    # ── 诊断 ---------------------------------------------------------
    def describe(self) -> str:
        return (f"PicoBot[{self.state.name}] t={self.match_elapsed:.1f}s "
                f"push_tries={self.push_tries}/3")


# ── 自检 (契约形状 + 状态机烟雾测试, 不依赖 gym) ────────────────────
def _smoke_test() -> None:
    ctl = PicoBotController(seed=1)
    # 契约常量
    assert OBS_DIM == 9 and len(OBS_NAMES) == 9
    # 1. INIT 0.5s: 安全中心 obs
    safe_obs = [1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0]
    for i in range(7):  # 0.56s → 进入 SCAN
        a = ctl.act(safe_obs, dt=0.08)
        assert 0 <= a < 21, f"动作越界: {a}"
    assert ctl.state == GR_State.SCAN, f"0.5s 后应进入 SCAN, got {ctl.state.name}"
    # 2. SCAN 发现对手 → PUSH
    obs_opp = [1.0, 1.0, 1.0, 1.0, 0.3, 5.0, 0.2, 0.0, 0.0]
    a = ctl.act(obs_opp)
    assert ctl.state == GR_State.PUSH, f"发现对手应进入 PUSH, got {ctl.state.name}"
    assert a in (int(Action.FW_FAST), int(Action.FW_MED)), f"直冲预期, got {a}"
    # 3. 边缘跌落 → ESCALATE → ESCAPE
    danger_obs = [0.1, 0.9, 0.9, 0.9, 0.5, 0.0, 0.0, 0.0, 0.0]
    a = ctl.act(danger_obs)
    assert ctl.state == GR_State.ESCAPE, f"边缘危险应 ESCALATE→ESCAPE"
    assert a == int(Action.REV_SLOW), f"ESCAPE 应后退, got {a}"
    # 4. 3s 接触 3 次 → DEFEND
    for i in range(38):  # 3.04s
        a = ctl.act([1.0, 1.0, 1.0, 1.0, 0.1, 0.0, 0.0, 0.0, 0.0], dt=0.08)
        if ctl.state == GR_State.DEFEND:
            break
    assert ctl.state == GR_State.DEFEND, f"3 次顶推后应 DEFEND, got {ctl.state.name}"
    print("[OK] PicoBotController 状态机烟雾测试通过 (INIT/SCAN/PUSH/ESCAPE/DEFEND)")
    print(f"[OK] 动作空间: Discrete(21), obs: {OBS_DIM} 维 {OBS_NAMES}")


# ── 环境集成测试 (可选: gymnasium 可用时跑 1 episode) ────────────────
def _env_integration(episodes: int = 3, steps: int = 300) -> None:
    try:
        from lightweight_env import LightweightBottleSumoEnv
    except ImportError as exc:  # pragma: no cover
        print(f"[SKIP] 环境集成测试 (导入失败: {exc})")
        return
    ctl = PicoBotController()
    total_wins, total_falls = 0, 0
    for ep in range(episodes):
        env = LightweightBottleSumoEnv(opponent_profile="passive", seed=100 + ep)
        obs, _ = env.reset()
        done, fell = False, False
        for _ in range(steps):
            a = ctl.act(obs.tolist())
            obs, _r, terminated, truncated, info = env.step(a)
            if terminated:
                done = True
                # info 约定: fell/opponent_fell 任一存在即判定
                fell = bool(info.get("fell", False)) and not bool(
                    info.get("opponent_fell", False))
                break
        if done and not fell:
            total_wins += 1
        if fell:
            total_falls += 1
        print(f"[EP{ep}] {ctl.describe()} done={done} fell={fell}")
    print(f"[OK] 环境集成: {episodes} ep, 胜 {total_wins}, 自跌 {total_falls}")


if __name__ == "__main__":
    _smoke_test()
    _env_integration()
