"""
mujoco_env.py — BottleSumo MuJoCo Physics Environment (Phase G / MuJoCo integration)

Real-physics twin of `lightweight_env.py` (which uses simplified kinematics).
Same Gym API: 7-dim observation, Discrete(21) actions, same reward semantics
(V10Reward), so the V9 gate evaluator / ABDL agent / G1 RViz bridge can be
pointed at either backend via `--backend mujoco`.

Physics differences vs lightweight_env:
  - Contacts computed by MuJoCo (soft contact model, friction, restitution)
  - Differential drive via wheel velocities (left/right wheel actuators)
  - Opponent is a second free body with its own strategy callback

Observation (7 dims, identical to lightweight_env):
  [edge_front, edge_back, edge_left, edge_right, opponent_dist,
   opponent_angle_deg, robot_speed]

Units: meters, radians, seconds. DOHYO_RADIUS=0.40, ROBOT_RADIUS=0.075.

Usage:
    from simulation.mujoco_env import MuJoCoBottleSumoEnv
    env = MuJoCoBottleSumoEnv(opponent_strategy=my_strategy_fn)
    obs, _ = env.reset(seed=42)
    obs, reward, term, trunc, info = env.step(21_action_int)
"""
from __future__ import annotations

import math
import random
from typing import Callable, Optional, Tuple

import numpy as np

try:
    import mujoco
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "mujoco not installed. Run: pip3 install --user mujoco  (WSL python3)"
    ) from exc

try:
    import gymnasium as gym
except ImportError:
    import gym

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wheel_to_discrete import Action, ACTION_MAP
from reward_functions import V10Reward, compute_heading_to_edge

DOHYO_RADIUS = 0.40
DOHYO_EDGE_ZONE = 0.08
DOHYO_SAFE_RADIUS = DOHYO_RADIUS - DOHYO_EDGE_ZONE
ROBOT_RADIUS = 0.075
TIMESTEP = 0.08  # gym step duration (s); MuJoCo internal dt = 0.004 -> 20 substeps
MAX_STEPS = 500

# Wheel geometry (Rev1 sim geometry, 34mm wheels; authority design_spec.json says 48mm (Rev2).
# Conflict status: PENDING_USER_ADJUDICATION — see .aionui/context/motor_consistency_audit.md)
WHEEL_RADIUS = 0.017
WHEEL_SEPARATION = 0.13
# N20 6V 300rpm (design_spec.json authority + WSL controller.yaml): 300/60*2pi = 31.4 rad/s.
# 34mm wheel -> 0.53 m/s max linear speed (matches controller.yaml "300RPM -> 0.53 m/s").
MAX_WHEEL_VEL = 31.4  # rad/s (= 300rpm no-load output speed)
# Servo sizing: max P torque Kp*MAX_WHEEL_VEL must exceed wheel spin-up friction
# mu*(m_robot/2)*g*R = 1.0*7.35*0.017 = 0.125 Nm; Kp=3e-3 -> 0.124 Nm (margin).
# Stability: Kp*dt/I_wheel = 3e-3*0.004/2.17e-5 = 0.55 < 1 -> stable servo.
# Integral term breaks static friction at LOW targets (e.g. turn: err=3.8 rad/s
# -> P torque only 0.011 Nm < 0.125 Nm stiction; integral ramps torque to 0.125).
# Leaky integrator: reset when |err| < deadband so no steady-state torque bias.
# Wheel static friction limit: mu*(m_robot/2)*g*R = 1.2*7.35*0.017 = 0.150 Nm.
# Caps MUST exceed it: motor 0.25 Nm, integral max 0.5 -> Ki*max = 0.25 Nm.
WHEEL_TORQUE_MAX = 0.25   # Nm per wheel (must exceed 0.150 Nm wheel stiction)
WHEEL_CTRL_GAIN = 0.003   # P gain Nm per (rad/s) error
WHEEL_CTRL_INTEGRAL_GAIN = 0.5  # I gain Nm per (rad/s * s) accumulated error
WHEEL_INTEGRAL_MAX = 0.5  # integral anti-windup cap (rad/s * s); Ki*max > stiction
WHEEL_ERR_DEADBAND = 0.5  # rad/s; below this the wheel tracks -> drop integral
# Opponent velocity servo (force-based, world frame). Must overcome its own
# static friction (0.5*9.81 = 4.9 N): gain 10 N/(m/s) -> 7 N at 0.7 m/s cmd.
# Thrust cap 8 N stays BELOW the robot's push force (~17.6 N traction) so the
# robot can physically shove it (opponent total resistance ~12.9 N < 17.6 N).
OPP_SERVO_GAIN = 10.0  # N per (m/s) velocity error
OPP_THRUST_MAX = 8.0   # N (max 8 m/s^2 accel on 1.0 kg puck)
OPP_ANG_GAIN = 0.5     # Nm per (rad/s) yaw error
OPP_TORQUE_MAX = 1.0   # Nm yaw cap
# qvel layout: robot_free(6) + wheel_l(1) + wheel_r(1) + opponent_free(6)
WHEEL_L_QVEL = 6
WHEEL_R_QVEL = 7

# MuJoCo XML: two cylinders (robot red, opponent blue) on a dohyo disc.
# Both have a free joint; "wheel" bodies are decorative + actuators apply
# differential drive torque derived from (linear, angular) commands.
MUJOCO_XML = """
<mujoco model="bottlesumo_dohyo">
  <option timestep="0.004" gravity="0 0 -9.81" density="1.2"
          cone="pyramidal"/>
  <default>
    <geom contype="1" conaffinity="1" friction="0.9 0.005 0.0001"/>
    <default class="wheel">
      <geom type="cylinder" size="0.017 0.01" mass="0.15"
            friction="1.2 0.05 0.001" rgba="0.2 0.2 0.2 1"/>
    </default>
  </default>
  <worldbody>
    <!-- Dohyo: static collidable disc, top at z=0; side wall keeps rolling edge.
         Sliding friction 0.5 (smooth dohyo). Contact mu = MAX(pair) in MuJoCo:
         wheels keep max(1.2, 0.5)=1.2, opponent puck gets max(0.5, 0.5)=0.5. -->
    <geom name="dohyo" type="cylinder" size="0.40 0.02" pos="0 0 -0.02"
          rgba="0.75 0.75 0.75 1" contype="1" conaffinity="1" friction="0.5 0.005 0.0001"/>
    <geom name="dohyo_ring" type="cylinder" size="0.402 0.021" pos="0 0 -0.021"
          rgba="0.9 0.2 0.2 1" contype="0" conaffinity="0"/>
    <!-- Catch-fall ground plane below the dohyo (fallen robots/opponents land here) -->
    <geom name="ground" type="plane" size="2 2 0.1" pos="0 0 -0.6"
          rgba="0.55 0.55 0.6 1" contype="1" conaffinity="1"/>
    <!-- Robot: chassis (r=0.045, 8mm ground clearance) + two driven wheels.
         Wheels on the LEFT/RIGHT (y=+-0.065, separation 0.13) with axle along
         Y (zaxis="0 1 0"); wheel centers at z=0.017 so bottoms touch dohyo at
         z=0; body bottom at z=0.008. -->
    <body name="robot" pos="0 0 0.03">
      <freejoint name="robot_free"/>
      <geom name="robot_body" type="cylinder" size="0.045 0.022" pos="0 0 0"
            rgba="0.9 0.2 0.2 0.95" mass="1.2"/>
      <body name="wheel_l" pos="0 0.065 -0.013">
        <joint name="wheel_l_joint" type="hinge" axis="0 1 0" limited="false"/>
        <geom class="wheel" zaxis="0 1 0"/>
      </body>
      <body name="wheel_r" pos="0 -0.065 -0.013">
        <joint name="wheel_r_joint" type="hinge" axis="0 1 0" limited="false"/>
        <geom class="wheel" zaxis="0 1 0"/>
      </body>
    </body>
    <!-- Opponent: single puck cylinder (velocity-controlled, no wheels).
         Sliding friction 0.5 (matches dohyo 0.5; contact mu = max(pair) = 0.5):
         smooth-dohyo sliding puck, pushable by the robot (real sumo dohyo). -->
    <body name="opponent" pos="0.2 0 0.03">
      <freejoint name="opponent_free"/>
      <geom name="opp_body" type="cylinder" size="0.075 0.03" pos="0 0 0"
            rgba="0.2 0.4 0.9 0.95" mass="1.0" friction="0.5 0.005 0.0001"/>
    </body>
  </worldbody>
  <actuator>
    <!-- Torque motors + Python PI velocity servo in step() (WHEEL_CTRL_GAIN,
         WHEEL_CTRL_INTEGRAL_GAIN). ctrl = torque (Nm), capped by ctrlrange
         (must match WHEEL_TORQUE_MAX = 0.25 > 0.150 Nm wheel stiction).
         (intvelocity/velocity actuators do not track in this contact setup.) -->
    <motor name="wheel_l" joint="wheel_l_joint" ctrlrange="-0.25 0.25" ctrllimited="true"/>
    <motor name="wheel_r" joint="wheel_r_joint" ctrlrange="-0.25 0.25" ctrllimited="true"/>
  </actuator>
</mujoco>
"""

# Body name lookup (spawned above the dohyo; z=0 is dohyo top).
# qpos layout: robot_free (7) + wheel_l (1) + wheel_r (1) + opponent_free (7)
ROBOT_QPOS_OFFSET = 0
OPP_QPOS_OFFSET = 7 + 1 + 1


def _signed_angle_diff(a: float, b: float) -> float:
    """Signed smallest angle from a to b, in radians."""
    d = (b - a + math.pi) % (2 * math.pi) - math.pi
    return d


class MuJoCoBottleSumoEnv(gym.Env):
    """
    MuJoCo-physics BottleSumo environment with 21-level action space.

    API-compatible with LightweightBottleSumoEnv:
      - reset(seed) -> (obs, info)
      - step(action) -> (obs, reward, terminated, truncated, info)
      - attributes: robot_x/y/theta, opponent_x/y/theta, action_space,
        observation_space
    """

    metadata = {"render_modes": ["none"], "render_fps": 10}

    def __init__(
        self,
        opponent_profile: str = "aggressive",
        render_mode: str = "none",
        seed: Optional[int] = None,
        edge_penalty_weight: float = 1.0,
        push_threshold: float = 0.2,
        opponent_strategy: Optional[Callable] = None,
        opponent_strategy_name: str = "aggressive",
    ):
        super().__init__()
        self.action_space = gym.spaces.Discrete(Action.size())
        self.observation_space = gym.spaces.Box(
            low=np.array([0.0, 0.0, 0.0, 0.0, 0.0, -180.0, -0.7], dtype=np.float32),
            high=np.array([1.0, 1.0, 1.0, 1.0, 4.0, 180.0, 0.7], dtype=np.float32),
            dtype=np.float32,
        )
        self.render_mode = render_mode
        self.reward_fn = V10Reward(
            edge_penalty_weight=edge_penalty_weight,
            push_threshold=push_threshold,
        )
        self.opponent_profile = opponent_profile
        self.opponent_strategy = opponent_strategy
        self.opponent_strategy_name = opponent_strategy_name
        self._seed = seed

        self.model = mujoco.MjModel.from_xml_string(MUJOCO_XML)
        self.data = mujoco.MjData(self.model)

        # actuator ids
        self._wheel_l_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_ACTUATOR, "wheel_l")
        self._wheel_r_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_ACTUATOR, "wheel_r")

        self.robot_x = 0.0
        self.robot_y = 0.0
        self.robot_theta = 0.0
        self.robot_speed = 0.0
        self.opponent_x = 0.0
        self.opponent_y = 0.0
        self.opponent_theta = 0.0
        self._episode_steps = 0
        self._step_buf = 0.0  # integrator substep accumulator
        # wheel PI servo integral state (anti-windup capped)
        self._int_l = 0.0
        self._int_r = 0.0

    # ── physics helpers ──

    def _sync_state(self):
        d = self.data
        # robot free joint qpos: [x, y, z, qw, qx, qy, qz] at ROBOT_QPOS_OFFSET
        self.robot_x = float(d.qpos[ROBOT_QPOS_OFFSET + 0])
        self.robot_y = float(d.qpos[ROBOT_QPOS_OFFSET + 1])
        qw, qx, qy, qz = d.qpos[ROBOT_QPOS_OFFSET + 3: ROBOT_QPOS_OFFSET + 7]
        # yaw from quaternion
        self.robot_theta = float(math.atan2(2 * (qw * qz + qx * qy), 1 - 2 * (qy * qy + qz * qz)))
        # opponent
        self.opponent_x = float(d.qpos[OPP_QPOS_OFFSET + 0])
        self.opponent_y = float(d.qpos[OPP_QPOS_OFFSET + 1])
        qw2, qx2, qy2, qz2 = d.qpos[OPP_QPOS_OFFSET + 3: OPP_QPOS_OFFSET + 7]
        self.opponent_theta = float(
            math.atan2(2 * (qw2 * qz2 + qx2 * qy2), 1 - 2 * (qy2 * qy2 + qz2 * qz2))
        )
        self.robot_speed = float(math.hypot(d.qvel[0], d.qvel[1]))

    def _get_obs(self) -> np.ndarray:
        """7-dim obs identical to lightweight_env (1.0 = safe, 0.0 = at edge).

        FIXED 2026-08-05 (queue #4 root cause): the previous direction-neutral
        edge sensors (all four = edge_norm(rim)) violated the cross-backend
        contract. lightweight_env has *directional* probes offset by ROBOT_RADIUS
        along heading/perpendicular, plus a full-arena linear ramp
        1.0 - dist/DOHYO_RADIUS*0.9. With direction-neutral sensors the ABDL
        rules built on min(edge_f..r) formed a dead zone (rim 0.128~0.16m,
        edge_prox 0.5~0.6) where no rule fired -> '?' FW_SLOW crawl -> timeouts
        (abdl 40% on MuJoCo vs 70% lightweight). This mirrors lightweight exactly.
        """
        dist_from_center = math.hypot(self.robot_x, self.robot_y)
        edge_danger = max(0.0, min(1.0, dist_from_center / DOHYO_RADIUS))

        def _on_dohyo(x: float, y: float) -> bool:
            return math.hypot(x, y) <= DOHYO_RADIUS

        def _edge(px: float, py: float) -> float:
            return 1.0 - edge_danger * 0.9 if _on_dohyo(px, py) else 0.0

        cos_t, sin_t = math.cos(self.robot_theta), math.sin(self.robot_theta)
        edge_front = _edge(self.robot_x + ROBOT_RADIUS * cos_t,
                           self.robot_y + ROBOT_RADIUS * sin_t)
        edge_back = _edge(self.robot_x - ROBOT_RADIUS * cos_t,
                          self.robot_y - ROBOT_RADIUS * sin_t)
        edge_left = _edge(self.robot_x - ROBOT_RADIUS * sin_t,
                          self.robot_y + ROBOT_RADIUS * cos_t)
        edge_right = _edge(self.robot_x + ROBOT_RADIUS * sin_t,
                           self.robot_y - ROBOT_RADIUS * cos_t)

        # opponent relative
        dx = self.opponent_x - self.robot_x
        dy = self.opponent_y - self.robot_y
        opp_dist = float(math.hypot(dx, dy))
        opp_angle_deg = float(math.degrees(_signed_angle_diff(self.robot_theta, math.atan2(dy, dx))))

        return np.array(
            [edge_front, edge_back, edge_left, edge_right,
             opp_dist, opp_angle_deg, float(np.clip(self.robot_speed, 0.0, 0.7))],
            dtype=np.float32,
        )

    # ── Gym API ──

    def reset(self, seed: Optional[int] = None, options: Optional[dict] = None):
        super().reset(seed=seed)
        self._episode_steps = 0
        self._int_l = 0.0
        self._int_r = 0.0
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)

        # F-109 fix (2026-08-07): align RNG consumption order + spawn
        # semantics with lightweight_env (Queue #4 cross-backend contract).
        # lightweight order: [robot_x, robot_y, angle_to_robot, dist,
        #   opp_jitter, robot_jitter] with BOTH robots facing each other.
        # Old mujoco order was [rx, ry, rth(random), ang, dist, opp_jitter]:
        #   the 3rd RNG draw had different meaning (random robot heading vs
        #   angle_to_robot), shifting dist to a different draw -> same-seed
        #   opp_dist diverged by ~0.127 (test_edge_obs_matches_lightweight_
        #   elementwise failure).
        # spawn robot near center, random offset
        rx = random.uniform(-0.05, 0.05)
        ry = random.uniform(-0.05, 0.05)
        # opponent inside ring facing robot
        ang = random.uniform(0, 2 * math.pi)
        dist = random.uniform(0.12, DOHYO_RADIUS * 0.7)
        ox = rx + dist * math.cos(ang)
        oy = ry + dist * math.sin(ang)
        oth = math.atan2(ry - oy, rx - ox) + random.uniform(-0.2, 0.2)
        # robot also spawns FACING the opponent (fair spawn, like sumo)
        rth = math.atan2(oy - ry, ox - rx) + random.uniform(-0.2, 0.2)

        d = self.data
        # body-frame origin at z=0.03 -> wheels touch dohyo top exactly (no free-fall)
        d.qpos[ROBOT_QPOS_OFFSET + 0: ROBOT_QPOS_OFFSET + 3] = [rx, ry, 0.03]
        d.qpos[ROBOT_QPOS_OFFSET + 3: ROBOT_QPOS_OFFSET + 7] = [math.cos(rth / 2), 0, 0, math.sin(rth / 2)]
        d.qpos[OPP_QPOS_OFFSET + 0: OPP_QPOS_OFFSET + 3] = [ox, oy, 0.03]
        d.qpos[OPP_QPOS_OFFSET + 3: OPP_QPOS_OFFSET + 7] = [math.cos(oth / 2), 0, 0, math.sin(oth / 2)]
        d.qvel[:] = 0.0
        mujoco.mj_forward(self.model, d)
        self._sync_state()
        return self._get_obs(), {}

    def step(self, action: int):
        self._episode_steps += 1

        linear, angular = ACTION_MAP.get(action, ACTION_MAP[Action.STOP])
        # differential drive -> wheel velocity targets (rad/s)
        v_l = (linear - angular * WHEEL_SEPARATION / 2) / WHEEL_RADIUS
        v_r = (linear + angular * WHEEL_SEPARATION / 2) / WHEEL_RADIUS
        target_wl = float(np.clip(v_l, -MAX_WHEEL_VEL, MAX_WHEEL_VEL))
        target_wr = float(np.clip(v_r, -MAX_WHEEL_VEL, MAX_WHEEL_VEL))

        # integrate: TIMESTEP (0.08s) in 0.004s substeps (20)
        n_sub = int(round(TIMESTEP / self.model.opt.timestep))
        d = self.data
        for _ in range(n_sub):
            # PI velocity servo at 250 Hz: torque = Kp*err + Ki*int(err), torque-limited.
            # Integral ramps torque past wheel static friction at low targets (turns).
            err_l = target_wl - d.qvel[WHEEL_L_QVEL]
            err_r = target_wr - d.qvel[WHEEL_R_QVEL]
            # leaky integral: only accumulates while NOT tracking (breaks stiction);
            # reset near target so no steady-state torque bias
            if abs(err_l) < WHEEL_ERR_DEADBAND:
                self._int_l = 0.0
            else:
                self._int_l = float(np.clip(self._int_l + err_l * self.model.opt.timestep, -WHEEL_INTEGRAL_MAX, WHEEL_INTEGRAL_MAX))
            if abs(err_r) < WHEEL_ERR_DEADBAND:
                self._int_r = 0.0
            else:
                self._int_r = float(np.clip(self._int_r + err_r * self.model.opt.timestep, -WHEEL_INTEGRAL_MAX, WHEEL_INTEGRAL_MAX))
            d.ctrl[self._wheel_l_id] = float(np.clip(
                WHEEL_CTRL_GAIN * err_l + WHEEL_CTRL_INTEGRAL_GAIN * self._int_l,
                -WHEEL_TORQUE_MAX, WHEEL_TORQUE_MAX))
            d.ctrl[self._wheel_r_id] = float(np.clip(
                WHEEL_CTRL_GAIN * err_r + WHEEL_CTRL_INTEGRAL_GAIN * self._int_r,
                -WHEEL_TORQUE_MAX, WHEEL_TORQUE_MAX))
            # opponent strategy -> force-based velocity servo on its freejoint.
            # (Real dynamic body: pushes CAN move it, unlike raw qvel writes.)
            # Thrust capped below the robot's push force so it can be shoved out.
            if self.opponent_strategy is not None:
                obs_now = self._get_obs()
                oa = self.opponent_strategy(obs_now, self._episode_steps)
                if isinstance(oa, tuple):
                    o_lin, o_ang = oa
                else:
                    o_lin, o_ang = ACTION_MAP.get(oa, (0.0, 0.0))
                OPP_QVEL = 6 + 1 + 1
                qo = self.data.qpos[OPP_QPOS_OFFSET + 3: OPP_QPOS_OFFSET + 7]
                h = math.atan2(2 * (qo[0] * qo[3] + qo[1] * qo[2]), 1 - 2 * (qo[2] ** 2 + qo[3] ** 2))
                err_vx = o_lin * math.cos(h) - self.data.qvel[OPP_QVEL + 0]
                err_vy = o_lin * math.sin(h) - self.data.qvel[OPP_QVEL + 1]
                err_w = o_ang - self.data.qvel[OPP_QVEL + 5]
                self.data.qfrc_applied[OPP_QVEL + 0] = float(np.clip(
                    OPP_SERVO_GAIN * err_vx, -OPP_THRUST_MAX, OPP_THRUST_MAX))
                self.data.qfrc_applied[OPP_QVEL + 1] = float(np.clip(
                    OPP_SERVO_GAIN * err_vy, -OPP_THRUST_MAX, OPP_THRUST_MAX))
                self.data.qfrc_applied[OPP_QVEL + 5] = float(np.clip(
                    OPP_ANG_GAIN * err_w, -OPP_TORQUE_MAX, OPP_TORQUE_MAX))
            mujoco.mj_step(self.model, self.data)

        self._sync_state()
        obs = self._get_obs()

        # out-of-bounds (V9 gate semantics): footprint EDGE reaches the rim,
        # i.e. center beyond DOHYO_RADIUS - 0.075, matching lightweight_env
        # (also caught when physically fallen off: z < -0.25)
        OUT_RADIUS = DOHYO_RADIUS - ROBOT_RADIUS  # 0.325
        robot_out = (math.hypot(self.robot_x, self.robot_y) > OUT_RADIUS
                     or self.data.qpos[ROBOT_QPOS_OFFSET + 2] < -0.25)
        opp_out = (math.hypot(self.opponent_x, self.opponent_y) > OUT_RADIUS
                   or self.data.qpos[OPP_QPOS_OFFSET + 2] < -0.25)

        heading_to_edge = compute_heading_to_edge(
            self.robot_theta, self.robot_x, self.robot_y, DOHYO_RADIUS
        )

        reward, done = self.reward_fn.compute(
            edge_sensors=(obs[0], obs[1], obs[2], obs[3]),
            opp_dist=obs[4],
            opp_angle=obs[5],
            speed=obs[6],
            heading_to_edge=heading_to_edge,
            opp_out_of_bounds=opp_out,
        )
        truncated = self._episode_steps >= MAX_STEPS
        # terminal: reward_fn "edge at rim" done OR robot fell OR opponent pushed out (win)
        # (mirrors lightweight_env: done is the termination signal)
        terminated = bool(done or robot_out or (opp_out and reward > 0))

        info = {
            "robot_x": self.robot_x, "robot_y": self.robot_y,
            "robot_theta": self.robot_theta,
            "opponent_x": self.opponent_x, "opponent_y": self.opponent_y,
            "robot_out": robot_out, "opp_out": opp_out,
            "steps": self._episode_steps,
        }
        return obs, float(reward), terminated, truncated, info
