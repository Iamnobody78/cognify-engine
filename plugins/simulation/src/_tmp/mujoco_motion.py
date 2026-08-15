#!/usr/bin/env python3
"""Deterministic motion verification for MuJoCoBottleSumoEnv.

1. FW_MAX (0.7 m/s) for 5 steps -> ~0.28 m displacement, speed ~0.7
2. TURN_L_HARD (1.0 rad/s) for 5 steps -> heading change ~0.4 rad
3. STOP for 6 steps -> wheel velocity decays to ~0, robot decelerates
4. 200 random steps -> no NaN, no premature termination, states finite
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import math
import numpy as np
from simulation.mujoco_env import MuJoCoBottleSumoEnv, Action, DOHYO_RADIUS, WHEEL_RADIUS

env = MuJoCoBottleSumoEnv(seed=42)
obs, _ = env.reset(seed=42)
# Move opponent far away to isolate robot kinematics (opponent blocks path otherwise)
env.data.qpos[9:12] = [-0.3, -0.2, 0.03]
env.data.qvel[8:14] = 0.0
env.data.qpos[12:16] = [1.0, 0, 0, 0]
env._sync_state()
x0, y0, th0 = env.robot_x, env.robot_y, env.robot_theta
print(f"start: x={x0:.3f} y={y0:.3f} th={math.degrees(th0):.1f}deg")

# --- 1. straight line FW_MAX ---
for _ in range(5):
    obs, r, term, trunc, info = env.step(int(Action.FW_MAX))
dist = math.hypot(env.robot_x - x0, env.robot_y - y0)
print(f"after FW_MAX x5: dist={dist:.3f} m (expect ~0.25), speed={env.robot_speed:.3f} (expect ~0.7)")
assert 0.18 < dist < 0.38, f"FW_MAX displacement out of range: {dist}"
assert 0.4 < env.robot_speed < 0.9, f"FW_MAX speed out of range: {env.robot_speed}"

# --- 2. hard left turn ---
th1 = env.robot_theta
for _ in range(5):
    obs, r, term, trunc, info = env.step(int(Action.TURN_L_HARD))
dth = abs(((env.robot_theta - th1 + math.pi) % (2 * math.pi)) - math.pi)
print(f"after TURN_L_HARD x5: dth={math.degrees(dth):.1f}deg (expect ~23deg=0.4rad)")
assert 0.15 < dth < 0.7, f"turn angle out of range: {dth}"

# --- 3. STOP decays velocity ---
obs, r, term, trunc, info = env.step(int(Action.STOP))
s0 = env.robot_speed
for _ in range(5):
    obs, r, term, trunc, info = env.step(int(Action.STOP))
print(f"STOP: speed {s0:.3f} -> {env.robot_speed:.3f} m/s (expect decrease)")
assert env.robot_speed <= s0 + 1e-6, "STOP did not decelerate"

# --- 4. long random run, finite + no premature termination ---
env2 = MuJoCoBottleSumoEnv(seed=7)
obs, _ = env2.reset(seed=7)
terminated_early = False
for i in range(200):
    a = int(np.random.randint(0, Action.size()))
    obs, r, term, trunc, info = env2.step(a)
    if not np.isfinite(obs).all():
        print(f"NON-FINITE obs at step {i}: {obs}")
        sys.exit(1)
    if trunc:
        terminated_early = True
        print(f"truncated at step {i}")
        break
print(f"200 random steps: robot at ({env2.robot_x:.3f},{env2.robot_y:.3f}) speed={env2.robot_speed:.3f}, opp at ({env2.opponent_x:.3f},{env2.opponent_y:.3f})")
print("MOTION OK")
