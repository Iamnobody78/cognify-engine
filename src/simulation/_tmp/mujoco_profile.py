#!/usr/bin/env python3
"""Profile FW_MAX acceleration: robot speed + wheel angular velocity per step."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from simulation.mujoco_env import MuJoCoBottleSumoEnv, Action, WHEEL_L_QVEL, WHEEL_R_QVEL

env = MuJoCoBottleSumoEnv(seed=42)
obs, _ = env.reset(seed=42)
print("step | robot_speed | wheel_w (L/R) | slip% | dist")
x0, y0 = env.robot_x, env.robot_y
for i in range(20):
    obs, r, term, trunc, info = env.step(int(Action.FW_MAX))
    wl = env.data.qvel[WHEEL_L_QVEL]
    wr = env.data.qvel[WHEEL_R_QVEL]
    w_avg = (wl + wr) / 2
    surf = w_avg * 0.017
    slip = max(0.0, 1 - env.robot_speed / surf) if surf > 1e-3 else 0.0
    dist = ((env.robot_x - x0) ** 2 + (env.robot_y - y0) ** 2) ** 0.5
    print(f"{i:4d} | {env.robot_speed:11.3f} | {wl:7.2f}/{wr:6.2f} | {slip:5.1%} | {dist:.3f}")
print("done:", term, trunc)
