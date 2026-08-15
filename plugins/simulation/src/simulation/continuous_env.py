"""
continuous_env.py — BottleSumo Continuous Action Environment

Extends LightweightBottleSumoEnv with Box(2) continuous action space.
Action: [linear_velocity ∈ [-0.7, 0.7], angular_velocity ∈ [-5.0, 5.0]]

Fully compatible with V10 reward functions and opponent profiles.
"""
import math
from typing import Tuple

import numpy as np
import gymnasium as gym

from lightweight_env import LightweightBottleSumoEnv, DOHYO_RADIUS, MAX_STEPS


class ContinuousBottleSumoEnv(LightweightBottleSumoEnv):
    """V11 BottleSumo environment with continuous action space.

    Inherits all V10 kinematics, observations, and reward logic.
    Only changes: action_space → Box(2), step() → continuous.

    Action: [linear_velocity (m/s), angular_velocity (rad/s)]
        linear ∈ [-0.7, 0.7]  — negative = reverse
        angular ∈ [-5.0, 5.0]  — negative = turn right, positive = turn left
    """

    ACTION_LINEAR_LOW = -0.7
    ACTION_LINEAR_HIGH = 0.7
    ACTION_ANGULAR_LOW = -5.0
    ACTION_ANGULAR_HIGH = 5.0

    def __init__(self, opponent_profile: str = "aggressive", render_mode: str = "none",
                 seed: int = None, edge_penalty_weight: float = 1.0,
                 push_threshold: float = 0.2,
                 allow_reverse: bool = True):
        """Continuous-action environment.

        Args:
            opponent_profile: "stationary"|"passive"|"moderate"|"aggressive"|"random"
            render_mode: "human"|"none"
            seed: random seed
            edge_penalty_weight: V10Reward edge penalty scale
            push_threshold: distance threshold for push bonus (meters)
            allow_reverse: if False, clamp linear to [0, 0.7]; useful for forward-only robots
        """
        self.allow_reverse = allow_reverse
        linear_low = self.ACTION_LINEAR_LOW if allow_reverse else 0.0

        # First set up parent without calling super().__init__() (we override spaces)
        # We manually init the parent
        LightweightBottleSumoEnv.__init__(
            self,
            opponent_profile=opponent_profile,
            render_mode=render_mode,
            seed=seed,
            edge_penalty_weight=edge_penalty_weight,
            push_threshold=push_threshold,
        )

        # Override action space with continuous
        self.action_space = gym.spaces.Box(
            low=np.array([linear_low, self.ACTION_ANGULAR_LOW], dtype=np.float32),
            high=np.array([self.ACTION_LINEAR_HIGH, self.ACTION_ANGULAR_HIGH], dtype=np.float32),
            dtype=np.float32,
        )

    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, bool, dict]:
        """Execute continuous action.

        Args:
            action: [linear_velocity, angular_velocity], unclipped raw from agent

        Returns:
            obs, reward, done, truncated, info (standard Gym API)
        """
        # Clip to valid range (safety, in case agent output exceeds bounds)
        linear = float(np.clip(action[0], self.action_space.low[0], self.action_space.high[0]))
        angular = float(np.clip(action[1], self.action_space.low[1], self.action_space.high[1]))

        self._episode_steps += 1

        # Move robot with continuous kinematics (inherited from parent)
        self._move_robot(linear, angular)

        # Move opponent
        self._move_opponent()

        # Collision physics
        self._resolve_collision()

        obs = self._get_obs()

        # Compute heading-to-edge for progressive reward
        from reward_functions import compute_heading_to_edge
        heading_to_edge = compute_heading_to_edge(
            self.robot_theta, self.robot_x, self.robot_y, DOHYO_RADIUS
        )

        # Check if opponent fell off
        opp_out = not self._is_on_dohyo(self.opponent_x, self.opponent_y)

        reward, done = self.reward_fn.compute(
            edge_sensors=(obs[0], obs[1], obs[2], obs[3]),
            opp_dist=obs[4],
            opp_angle=obs[5],
            speed=obs[6],
            heading_to_edge=heading_to_edge,
            opp_out_of_bounds=opp_out,
        )
        truncated = self._episode_steps >= MAX_STEPS

        info = {
            "episode_steps": self._episode_steps,
            "edge_margin": obs[0:4].min(),
            "opponent_dist": obs[4],
            "robot_speed": self.robot_speed,
            "action_linear": linear,
            "action_angular": angular,
        }

        return obs, reward, done, truncated, info


# ── Quick Smoke Test ──
if __name__ == "__main__":
    print("=" * 60)
    print(" BottleSumo V11 ContinuousBottleSumoEnv — Box(2) action space")
    print("=" * 60)

    env = ContinuousBottleSumoEnv(opponent_profile="aggressive", seed=42)

    print(f"\nAction space:    {env.action_space}")
    print(f"  linear range:  [{env.ACTION_LINEAR_LOW}, {env.ACTION_LINEAR_HIGH}]")
    print(f"  angular range: [{env.ACTION_ANGULAR_LOW}, {env.ACTION_ANGULAR_HIGH}]")
    print(f"Observation space: {env.observation_space.shape}")

    # Test reset + step
    obs, _ = env.reset()
    print(f"\nInitial obs: {np.round(obs, 3)}")

    for i in range(5):
        a = env.action_space.sample()
        obs, reward, done, truncated, info = env.step(a)
        print(f"  Step {i}: a=[{a[0]:.2f}, {a[1]:.2f}] "
              f"r={reward:.1f} done={done} speed={info['robot_speed']:.2f}")

    env.close()
    print("\n[OK] Continuous environment ready for TD3/SAC/PPO training")
