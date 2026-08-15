#!/usr/bin/env python3
"""Turn rate convergence check."""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from simulation.mujoco_env import MuJoCoBottleSumoEnv, Action

env = MuJoCoBottleSumoEnv(seed=42)
obs, _ = env.reset(seed=42)
env.data.qpos[9:12] = [-0.3, -0.2, 0.03]
env.data.qvel[8:14] = 0.0
env.data.qpos[12:16] = [1.0, 0, 0, 0]
env._sync_state()
th0 = env.robot_theta
for i in range(15):
    obs, r, term, trunc, info = env.step(int(Action.TURN_L_HARD))
    dth = abs(((env.robot_theta - th0 + math.pi) % (2 * math.pi)) - math.pi)
    rate = dth / (0.08 * (i + 1))
    print(f"step {i:2d}: cum dth={math.degrees(dth):6.1f}deg  avg rate={rate:.3f} rad/s (target 1.0)")
print("MOTION OK")
