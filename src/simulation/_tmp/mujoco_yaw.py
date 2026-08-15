#!/usr/bin/env python3
"""Measure robot freejoint constraint forces during TURN_L_HARD."""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import mujoco
from simulation.mujoco_env import MuJoCoBottleSumoEnv, Action, WHEEL_L_QVEL, WHEEL_R_QVEL

env = MuJoCoBottleSumoEnv(seed=42)
obs, _ = env.reset(seed=42)
env.data.qpos[9:12] = [-0.3, -0.2, 0.03]
env.data.qvel[8:14] = 0.0
env.data.qpos[12:16] = [1.0, 0, 0, 0]
env._sync_state()
m, d = env.model, env.data

# manually drive one gym step of TURN_L_HARD with per-substep detail
linear, angular = 0.0, 1.0
v_l = (linear - angular * 0.13 / 2) / 0.017
v_r = (linear + angular * 0.13 / 2) / 0.017
target_wl = float(min(max(v_l, -41.2), 41.2))
target_wr = float(min(max(v_r, -41.2), 41.2))
print(f"targets: wl={target_wl:.2f} wr={target_wr:.2f}")

n_sub = int(round(0.08 / m.opt.timestep))
for i in range(n_sub):
    err_l = target_wl - d.qvel[WHEEL_L_QVEL]
    err_r = target_wr - d.qvel[WHEEL_R_QVEL]
    env._int_l = min(max(env._int_l + err_l * m.opt.timestep, -0.5), 0.5)
    env._int_r = min(max(env._int_r + err_r * m.opt.timestep, -0.5), 0.5)
    d.ctrl[0] = min(max(0.003 * err_l + 0.5 * env._int_l, -0.25), 0.25)
    d.ctrl[1] = min(max(0.003 * err_r + 0.5 * env._int_r, -0.25), 0.25)
    mujoco.mj_step(m, d)
    if i in (0, 4, 9, 19):
        print(f"sub{i}: rob_v=({d.qvel[0]:6.3f},{d.qvel[1]:6.3f}) w_z={d.qvel[5]:7.4f} "
              f"wl={d.qvel[WHEEL_L_QVEL]:6.2f} wr={d.qvel[WHEEL_R_QVEL]:6.2f}")
        print(f"      qc_rob=({d.qfrc_constraint[0]:7.3f},{d.qfrc_constraint[1]:7.3f},{d.qfrc_constraint[5]:7.4f}) "
              f"qc_wl={d.qfrc_constraint[WHEEL_L_QVEL]:7.4f} qc_wr={d.qfrc_constraint[WHEEL_R_QVEL]:7.4f} "
              f"qa_rob=({d.qfrc_actuator[0]:6.3f},{d.qfrc_actuator[1]:6.3f},{d.qfrc_actuator[5]:6.4f})")

print(f"\nfinal: pos=({d.qpos[0]:.4f},{d.qpos[1]:.4f}) z={d.qpos[2]:.4f} th={math.degrees(env.robot_theta):.2f}")
