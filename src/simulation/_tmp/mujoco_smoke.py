#!/usr/bin/env python3
"""Smoke test for MuJoCoBottleSumoEnv: random actions, verify physics."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import numpy as np
from simulation.mujoco_env import MuJoCoBottleSumoEnv, Action, DOHYO_RADIUS

env = MuJoCoBottleSumoEnv(seed=42)
obs, info = env.reset(seed=42)
print("obs dim:", obs.shape, "dtype:", obs.dtype)
print("obs[0:4] (edges, 1=safe):", [round(float(x), 3) for x in obs[0:4]])
print("obs[4] opp_dist:", round(float(obs[4]), 3))
print("obs[5] opp_angle_deg:", round(float(obs[5]), 2))

# run 50 random steps, verify state changes & stays finite
for i in range(50):
    a = int(np.random.randint(0, Action.size()))
    obs, reward, term, trunc, info = env.step(a)
    if not np.isfinite(obs).all():
        print("NON-FINITE obs at step", i)
        break
    if term or trunc:
        print(f"done at step {i}: term={term} trunc={trunc} reward={reward:.2f}")
        break

print("final robot pos:", round(env.robot_x, 3), round(env.robot_y, 3), "th:", round(env.robot_theta, 3))
print("final opp pos:  ", round(env.opponent_x, 3), round(env.opponent_y, 3))
print("robot_speed:", round(env.robot_speed, 3))

# physics check: robot should have moved from origin
moved = abs(env.robot_x) + abs(env.robot_y) > 0.005
print("PHYSICS OK (robot moved):", moved)

# edge sensor sanity: at center edges should be ~1.0, near rim ~0
env2 = MuJoCoBottleSumoEnv(seed=7)
obs2, _ = env2.reset(seed=7)
print("center edges (expect ~1):", [round(float(x), 2) for x in obs2[0:4]])
env2.data.qpos[0] = 0.35  # near rim
env2.data.qpos[1] = 0.0
env2._sync_state()
obs3 = env2._get_obs()
print("rim edges (expect <0.2):", [round(float(x), 2) for x in obs3[0:4]])
print("SMOKE OK")
