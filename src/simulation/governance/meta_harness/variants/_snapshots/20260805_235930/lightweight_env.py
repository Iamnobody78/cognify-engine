"""
lightweight_env.py — BottleSumo V10 Lightweight Gym Environment

A self-contained Gymnasium environment for fast DQN training and heuristic testing.
21-level action space via wheel_to_discrete. No Gazebo/ROS2 dependency.
Uses simplified kinematics + physics for rapid iteration.
"""

import math
import random
import time
from typing import Dict, Tuple, Optional, Callable

import numpy as np

try:
    import gymnasium as gym
except ImportError:
    import gym

# Import V10 action space + reward
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wheel_to_discrete import (
    Action,
    ACTION_MAP,
    ACTION_GROUPS,
    SAFE_ACTIONS_WHEN_EDGE_CLOSE,
    heuristic_policy_v10,
)
from reward_functions import V10Reward, compute_heading_to_edge

# ── Dohyo (Sumo Ring) Constants ──
DOHYO_RADIUS = 0.40  # 40cm half-diameter (80cm total)
DOHYO_EDGE_ZONE = 0.08  # 8cm edge danger zone
DOHYO_SAFE_RADIUS = DOHYO_RADIUS - DOHYO_EDGE_ZONE  # 32cm — safe inner zone
ROBOT_RADIUS = 0.075  # 7.5cm robot half-width

# ── Simulation Constants ──
TIMESTEP = 0.08  # 80ms per step (matches Gazebo physics step)
MAX_STEPS = 500  # max episode length
OPPONENT_SPEEDS = {  # opponent behavior profiles
    "stationary": (0.0, 0.0, 0.0),
    "passive": (0.05, 0.1, 0.3),
    "moderate": (0.1, 0.3, 0.5),
    "aggressive": (0.2, 0.5, 0.7),
}
OPPONENT_PROFILES = list(OPPONENT_SPEEDS.keys())


class LightweightBottleSumoEnv(gym.Env):
    """
    V10 BottleSumo environment with 21-level action space.

    Observation (7 dims):
        [edge_front, edge_back, edge_left, edge_right,
         opponent_dist, opponent_angle, robot_speed]

    Action:
        Discrete(21) — wheel_to_discrete.Action enum

    State (internal, not observed directly):
        robot_x, robot_y, robot_theta, opponent_x, opponent_y
    """

    metadata = {"render_modes": ["human", "none"], "render_fps": 10}

    def __init__(
        self,
        opponent_profile: str = "aggressive",
        render_mode: str = "none",
        seed: int = None,
        edge_penalty_weight: float = 1.0,
        push_threshold: float = 0.2,
        opponent_strategy: Optional[Callable] = None,
    ):
        super().__init__()

        # ── Spaces ──
        self.action_space = gym.spaces.Discrete(Action.size())
        self.observation_space = gym.spaces.Box(
            low=np.array([0.0, 0.0, 0.0, 0.0, 0.0, -180.0, -0.7], dtype=np.float32),
            high=np.array([1.0, 1.0, 1.0, 1.0, 4.0, 180.0, 0.7], dtype=np.float32),
            dtype=np.float32,
        )

        self.opponent_profile = opponent_profile
        self.render_mode = render_mode
        self._seed = seed
        self.reward_fn = V10Reward(
            edge_penalty_weight=edge_penalty_weight,
            push_threshold=push_threshold,
        )  # V10 progressive edge reward with BayesOpt params
        if seed is not None:
            np.random.seed(seed)
            random.seed(seed)

        # Internal state
        self.robot_x = 0.0
        self.robot_y = 0.0
        self.robot_theta = 0.0
        self.robot_speed = 0.0
        self.opponent_x = 0.0
        self.opponent_y = 0.0
        self.opponent_theta = 0.0
        self._episode_steps = 0
        self._opponent_profile = opponent_profile
        # External strategy override (used by V9 gate evaluator):
        # callable (obs, step) -> discrete action; if set, _move_opponent uses it.
        self.opponent_strategy = opponent_strategy

    # ── Gym API ──

    def reset(self, seed: int = None, options: dict = None) -> Tuple[np.ndarray, dict]:
        super().reset(seed=seed)
        self._episode_steps = 0

        # Randomize opponent profile unless explicitly set in __init__
        if seed is not None:
            random.seed(seed)
        if self.opponent_profile == "random":
            self._opponent_profile = random.choice(OPPONENT_PROFILES)
        else:
            self._opponent_profile = self.opponent_profile

        # Place robot at center, random heading
        self.robot_x = random.uniform(-0.05, 0.05)
        self.robot_y = random.uniform(-0.05, 0.05)
        self.robot_speed = 0.0

        # Place opponent inside the ring, facing the robot (was: up to
        # DOHYO_RADIUS+0.2 away → spawned OUTSIDE the 0.40m ring and
        # self-destructed on the first move — fixed 2026-08-05).
        angle_to_robot = random.uniform(0, 2 * math.pi)
        dist = random.uniform(0.12, DOHYO_RADIUS * 0.7)
        self.opponent_x = self.robot_x + dist * math.cos(angle_to_robot)
        self.opponent_y = self.robot_y + dist * math.sin(angle_to_robot)
        self.opponent_theta = math.atan2(
            self.robot_y - self.opponent_y, self.robot_x - self.opponent_x
        ) + random.uniform(-0.2, 0.2)
        self.opponent_speed = 0.0

        # FIXED 2026-08-05: robot also spawns FACING the opponent (was random
        # heading 0..2π). The opponent always spawned facing the robot; the
        # robot's random heading meant ~50% of episodes started with the robot
        # turning around (pure spin = ZERO wheel thrust). Under the thrust-based
        # collision, a charging opponent hit a zero-thrust robot mid-turn and
        # shoved it out in <10 steps (defensive regression 2/2 -> 0/2).
        # Fair spawn: both robots face each other, like real sumo.
        self.robot_theta = math.atan2(
            self.opponent_y - self.robot_y, self.opponent_x - self.robot_x
        ) + random.uniform(-0.2, 0.2)

        return self._get_obs(), {}

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, dict]:
        self._episode_steps += 1

        # ── Move robot ──
        linear, angular = ACTION_MAP.get(action, ACTION_MAP[Action.STOP])
        self._move_robot(linear, angular)

        # ── Move opponent ──
        self._move_opponent()

        # ── Collision physics (push) ──
        self._resolve_collision()

        obs = self._get_obs()

        # Compute heading-to-edge for progressive reward
        heading_to_edge = compute_heading_to_edge(
            self.robot_theta, self.robot_x, self.robot_y, DOHYO_RADIUS
        )

        # Check if opponent fell off
        opp_out = not self._is_on_dohyo(self.opponent_x, self.opponent_y)
        # FIXED 2026-08-05: authoritative robot fall = CENTER beyond ring edge.
        # Previously V10Reward inferred death from probe sensors (a probe 7.5cm
        # ahead crossed the rim at center r>0.325 — the robot 'died' while 75%
        # of its body was still on the dohyo). Pass the env's exact check.
        robot_out = not self._is_on_dohyo(self.robot_x, self.robot_y)

        reward, done = self.reward_fn.compute(
            edge_sensors=(obs[0], obs[1], obs[2], obs[3]),
            opp_dist=obs[4],
            opp_angle=obs[5],
            speed=obs[6],
            heading_to_edge=heading_to_edge,
            opp_out_of_bounds=opp_out,
            robot_out_of_bounds=robot_out,
        )
        truncated = self._episode_steps >= MAX_STEPS

        info = {
            "episode_steps": self._episode_steps,
            "edge_margin": obs[0:4].min(),
            "opponent_dist": obs[4],
            "robot_speed": self.robot_speed,
            "action": action,
        }

        return obs, reward, done, truncated, info

    # ── Kinematics ──

    def _move_robot(self, linear: float, angular: float):
        """Differential drive kinematics."""
        self.robot_theta += angular * TIMESTEP
        self.robot_theta = self.robot_theta % (2 * math.pi)

        dx = linear * math.cos(self.robot_theta) * TIMESTEP
        dy = linear * math.sin(self.robot_theta) * TIMESTEP
        self.robot_x += dx
        self.robot_y += dy
        self.robot_speed = linear

    def _move_opponent(self):
        """Simple opponent behavior."""
        # External strategy override: action-based opponent (robot-like motion).
        if self.opponent_strategy is not None:
            # FIXED 2026-08-05: opponent now observes from ITS OWN frame
            # (was self._get_obs() = robot frame → aggressive turned AWAY when the
            # robot approached from its right side).
            obs = self._get_obs_for(
                self.opponent_x, self.opponent_y, self.opponent_theta,
                getattr(self, "opponent_speed", 0.0),
                self.robot_x, self.robot_y,
            )
            action = self.opponent_strategy(obs, self._episode_steps)
            linear, angular = ACTION_MAP.get(action, ACTION_MAP[Action.STOP])
            self.opponent_theta = (self.opponent_theta + angular * TIMESTEP) % (2 * math.pi)
            self.opponent_x += linear * math.cos(self.opponent_theta) * TIMESTEP
            self.opponent_y += linear * math.sin(self.opponent_theta) * TIMESTEP
            self.opponent_speed = linear
            return

        profile = OPPONENT_SPEEDS[self._opponent_profile]
        max_speed, turn_rate, aggression = profile

        # Opponent strategy: approach robot
        dx = self.robot_x - self.opponent_x
        dy = self.robot_y - self.opponent_y
        target_angle = math.atan2(dy, dx)

        # Angle error
        angle_err = (target_angle - self.opponent_theta + math.pi) % (2 * math.pi) - math.pi

        if abs(angle_err) > turn_rate:
            self.opponent_theta += turn_rate * math.copysign(1, angle_err) * TIMESTEP * 5
        else:
            # Facing robot — approach
            dist = math.hypot(dx, dy)
            if dist > 0.15:
                speed = max_speed * aggression
            else:
                speed = max_speed * aggression * 0.5  # slow down near robot
            self.opponent_x += speed * math.cos(self.opponent_theta) * TIMESTEP
            self.opponent_y += speed * math.sin(self.opponent_theta) * TIMESTEP

        self.opponent_theta = self.opponent_theta % (2 * math.pi)

    def _resolve_collision(self):
        """Sumo-style drive-vs-drive push contest.

        FIXED 2026-08-05: the previous fully-symmetric push (both robots displaced
        by overlap*0.5) made equal-speed counter-charges (aggressive opponent at
        FW_MAX) a PERMANENT stalemate — empirically NO policy could exit within
        MAX_STEPS (pure-ram 5/5 "wins" were 240-step timeouts, reward-inflation
        artifacts; reward at push steps topped at ~12.7 with zero exits).
        Physics reality: equal masses + equal speeds are symmetric under momentum
        conservation, so the winner in real sumo comes from WHEEL THRUST and
        TRACTION, not bounce. New model:
          * each body's wheel thrust (drive speed projected onto the contact
            normal) presses the other;
          * traction degrades linearly from DOHYO_SAFE_RADIUS to the ring edge
            (realistic: a robot shoved toward the rim loses wheel purchase and
            cannot resist);
          * the net thrust difference decides who gains ground.
        This restores the core sumo mechanic: a robot that drives harder into the
        contact, or that has better footing, actually moves the opponent.
        """
        dx = self.robot_x - self.opponent_x
        dy = self.robot_y - self.opponent_y
        dist = math.hypot(dx, dy)
        if dist < ROBOT_RADIUS * 2 and dist > 0.001:
            overlap = ROBOT_RADIUS * 2 - dist
            nx, ny = dx / dist, dy / dist  # unit normal: opponent -> robot

            def _traction(pos_x: float, pos_y: float) -> float:
                """Wheel grip: full inside safe zone, linear loss toward the rim."""
                r = math.hypot(pos_x, pos_y)
                if r >= DOHYO_RADIUS:
                    return 0.0
                return max(0.0, min(1.0, (DOHYO_RADIUS - r) / DOHYO_EDGE_ZONE))

            # Wheel thrust projected onto the contact normal.
            # Robot driving along -n presses the opponent along +n; opponent
            # driving along +n presses the robot along -n.
            rx = self.robot_speed * math.cos(self.robot_theta)
            ry = self.robot_speed * math.sin(self.robot_theta)
            ox = getattr(self, "opponent_speed", 0.0) * math.cos(self.opponent_theta)
            oy = getattr(self, "opponent_speed", 0.0) * math.sin(self.opponent_theta)

            thrust_r_on_o = max(0.0, -(rx * nx + ry * ny)) * _traction(self.robot_x, self.robot_y)
            thrust_o_on_r = max(0.0, (ox * nx + oy * ny)) * _traction(self.opponent_x, self.opponent_y)

            net = thrust_r_on_o - thrust_o_on_r
            momentum = net * TIMESTEP * 0.8

            push_opp = overlap * 0.5 + momentum    # opponent displaced along +n
            push_robot = overlap * 0.5 - momentum  # robot retreats less (or gains)

            self.robot_x += nx * push_robot
            self.robot_y += ny * push_robot
            self.opponent_x -= nx * push_opp
            self.opponent_y -= ny * push_opp

    # ── Observations ──

    def _get_obs(self) -> np.ndarray:
        """Compute 7-dim observation from the ROBOT's frame (kept for compat)."""
        return self._get_obs_for(
            self.robot_x, self.robot_y, self.robot_theta, self.robot_speed,
            self.opponent_x, self.opponent_y,
        )

    def _get_obs_for(
        self,
        x: float, y: float, theta: float, speed: float,
        other_x: float, other_y: float,
    ) -> np.ndarray:
        """Compute 7-dim observation from an arbitrary pose (robot OR opponent frame).

        Used by _get_obs() (robot frame) and _move_opponent (opponent frame), so the
        opponent strategy sees the world from ITS OWN heading — fixing the previous
        frame inversion that made the aggressive opponent turn AWAY from the robot.
        """
        # Edge sensors (simulated by distance from dohyo center)
        # FIXED 2026-08-05: was (dist - DOHYO_SAFE_RADIUS)/DOHYO_EDGE_ZONE which
        # only started warning at 0.32m — exactly where the center already falls
        # (0.40 - ROBOT_RADIUS = 0.325). Sensors were effectively DEAD inside the
        # playable area, so ABDL L0 edge rules never fired and the robot drove off.
        # Now: linear ramp 0.0 (center) -> 1.0 (ring edge) across the full arena.
        dist_from_center = math.hypot(x, y)
        edge_danger = max(0.0, min(1.0, dist_from_center / DOHYO_RADIUS))

        # Simulate 4 edge sensors (front/back/left/right relative to observer heading)
        edge_front = (
            1.0 - edge_danger * 0.9
            if self._is_on_dohyo(
                x + ROBOT_RADIUS * math.cos(theta),
                y + ROBOT_RADIUS * math.sin(theta),
            )
            else 0.0
        )
        edge_back = (
            1.0 - edge_danger * 0.9
            if self._is_on_dohyo(
                x - ROBOT_RADIUS * math.cos(theta),
                y - ROBOT_RADIUS * math.sin(theta),
            )
            else 0.0
        )
        edge_left = (
            1.0 - edge_danger * 0.9
            if self._is_on_dohyo(
                x - ROBOT_RADIUS * math.sin(theta),
                y + ROBOT_RADIUS * math.cos(theta),
            )
            else 0.0
        )
        edge_right = (
            1.0 - edge_danger * 0.9
            if self._is_on_dohyo(
                x + ROBOT_RADIUS * math.sin(theta),
                y - ROBOT_RADIUS * math.cos(theta),
            )
            else 0.0
        )

        # "Opponent" = the other body relative to this observer
        dx = other_x - x
        dy = other_y - y
        opp_dist = math.hypot(dx, dy)
        opp_angle_global = math.atan2(dy, dx)
        opp_angle_rel = math.degrees(
            (opp_angle_global - theta + math.pi) % (2 * math.pi) - math.pi
        )

        return np.array(
            [
                edge_front,
                edge_back,
                edge_left,
                edge_right,
                min(opp_dist, 4.0),  # cap at 4.0 (ToF max range)
                opp_angle_rel,
                speed,
            ],
            dtype=np.float32,
        )

    def _is_on_dohyo(self, x: float, y: float) -> bool:
        """Check if a point is within the dohyo."""
        return math.hypot(x, y) <= DOHYO_RADIUS

    # ── Reward ──

    def _compute_reward(self, obs: np.ndarray) -> Tuple[float, bool]:
        edge_f, edge_b, edge_l, edge_r = obs[0], obs[1], obs[2], obs[3]
        opp_dist = obs[4]
        opp_angle = obs[5]
        speed = obs[6]

        reward = 0.0
        done = False

        # ── Terminal conditions ──
        # Robot out-of-bounds
        if edge_f < 0.3 or edge_b < 0.3 or edge_l < 0.3 or edge_r < 0.3:
            return -100.0, True

        # Opponent out-of-bounds (win)
        if not self._is_on_dohyo(self.opponent_x, self.opponent_y):
            return 200.0, True

        # ── Continuous rewards ──

        # 1. Approach reward: closer to opponent = better
        if opp_dist < 1.0 and opp_dist > 0.02:
            # Exponential reward for getting close
            approach_reward = 3.0 * (1.0 - opp_dist)  # max 3.0 at 0m, 0 at 1m
            reward += approach_reward

        # 2. Alignment reward: facing opponent = better
        if opp_dist < 0.5:
            angle_penalty = abs(opp_angle) / 180.0  # 0 to 1
            alignment_reward = 2.0 * (1.0 - angle_penalty)  # max 2.0 when facing, 0 when ±180°
            reward += alignment_reward

        # 3. Push bonus: at contact distance
        if opp_dist < ROBOT_RADIUS * 2.2 and abs(opp_angle) < 45:
            if speed > 0.3:
                reward += 5.0  # strong push

        # 4. Edge penalty: staying near center = better
        edge_margin = min(edge_f, edge_b, edge_l, edge_r)
        if edge_margin < 0.7:
            reward -= 2.0 * (0.7 - edge_margin)  # up to -1.4 when at edge
        if edge_margin < 0.4:
            reward -= 5.0  # heavy penalty near edge

        # 5. Survival bonus
        reward += 0.1

        # 6. Energy efficiency penalty (discourage constant max speed)
        if speed > 0.5:
            reward -= 0.05

        return reward, done

    def close(self):
        pass

    def render(self):
        if self.render_mode == "none":
            return
        # ASCII render for debugging
        grid_size = 20
        grid = [["." for _ in range(grid_size)] for _ in range(grid_size)]
        cx, cy = grid_size // 2, grid_size // 2
        scale = grid_size / (2 * DOHYO_RADIUS)

        rx = int(cx + self.robot_x * scale)
        ry = int(cy + self.robot_y * scale)
        ox = int(cx + self.opponent_x * scale)
        oy = int(cy + self.opponent_y * scale)

        if 0 <= rx < grid_size and 0 <= ry < grid_size:
            grid[ry][rx] = "R"
        if 0 <= ox < grid_size and 0 <= oy < grid_size:
            grid[oy][ox] = "O"

        print(f"\nStep {self._episode_steps}: R=robot O=opponent .=")
        for row in grid:
            print(" ".join(row))
        print(
            f"Robot: ({self.robot_x:.2f}, {self.robot_y:.2f}) θ={math.degrees(self.robot_theta):.0f}°"
        )
        print(f"Opponent: ({self.opponent_x:.2f}, {self.opponent_y:.2f})")


# ── Evaluation Harness ──


def evaluate_heuristic_policy(
    env: LightweightBottleSumoEnv, policy_fn, n_episodes: int = 10, verbose: bool = True
) -> dict:
    """
    Evaluate a heuristic policy over n_episodes.
    Returns: {win_rate, avg_reward, avg_steps, avg_opponent_dist, edge_violations}
    """
    wins = 0
    total_reward = 0.0
    total_steps = 0
    total_opp_dist = 0.0
    edge_violations = 0

    for ep in range(n_episodes):
        obs, _ = env.reset()
        done = False
        ep_reward = 0.0
        ep_steps = 0
        ep_opp_dists = []

        while not done:
            opp_dist = obs[4]
            opp_angle = obs[5]
            edge_margin = obs[0:4].min()
            ep_opp_dists.append(opp_dist)

            action = policy_fn(opp_angle, opp_dist, edge_margin)
            obs, reward, done, truncated, info = env.step(action)
            ep_reward += reward
            ep_steps += 1

            if done and reward > 100:
                wins += 1
                break
            if done and reward < -50:
                edge_violations += 1
                break
            if truncated:
                break

        total_reward += ep_reward
        total_steps += ep_steps
        total_opp_dist += np.mean(ep_opp_dists) if ep_opp_dists else 4.0

    return {
        "win_rate_pct": wins / n_episodes * 100,
        "avg_reward": total_reward / n_episodes,
        "avg_steps": total_steps / n_episodes,
        "avg_opponent_dist": total_opp_dist / n_episodes,
        "edge_violations": edge_violations,
        "wins": wins,
        "total": n_episodes,
    }


# ── Main Test ──

if __name__ == "__main__":
    print("=" * 60)
    print(" BottleSumo V10 LightweightEnv — 21-level action space")
    print("=" * 60)

    env = LightweightBottleSumoEnv(opponent_profile="aggressive", render_mode="none", seed=42)

    print(f"\nAction space: {env.action_space}")
    print(f"Observation space: {env.observation_space.shape}")

    # Test reset + step
    obs, _ = env.reset()
    print(f"\nInitial obs: {obs}")

    for i in range(5):
        action = env.action_space.sample()
        obs, reward, done, truncated, info = env.step(action)
        print(f"  Step {i}: action={action}({Action(action).name}) reward={reward:.1f} done={done}")

    env.close()

    # Evaluate heuristic policy
    print("\n" + "=" * 60)
    print(" Evaluating V10 heuristic_policy_v10 (21-level)")
    print("=" * 60)

    for profile in OPPONENT_PROFILES:
        env2 = LightweightBottleSumoEnv(opponent_profile=profile, seed=42)
        result = evaluate_heuristic_policy(env2, heuristic_policy_v10, n_episodes=10, verbose=False)
        print(
            f"\n  vs {profile:<12s}: win_rate={result['win_rate_pct']:.0f}% "
            f"avg_reward={result['avg_reward']:.1f} "
            f"avg_steps={result['avg_steps']:.0f} "
            f"edges={result['edge_violations']}"
        )
        env2.close()

    print("\n✅ V10 lightweight environment ready for DQN training")
