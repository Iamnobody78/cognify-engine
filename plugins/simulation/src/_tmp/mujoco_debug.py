#!/usr/bin/env python3
"""Debug: why does the robot not move under the P servo?"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import numpy as np
import mujoco
from simulation.mujoco_env import MuJoCoBottleSumoEnv, Action, WHEEL_L_QVEL, WHEEL_R_QVEL

env = MuJoCoBottleSumoEnv(seed=42)
obs, _ = env.reset(seed=42)
d = env.data
m = env.model

print(f"nq={m.nq} nv={m.nv} nu={m.nu}")
print(f"wheel_l_id={env._wheel_l_id} wheel_r_id={env._wheel_r_id}")
print(f"actuator names: {[mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_ACTUATOR, i) for i in range(m.nu)]}")
print(f"qpos[:13]={d.qpos[:13]}")
print(f"ctrl={d.ctrl}")

# single step FW_MAX with per-substep logging
linear, angular = 0.7, 0.0
v_l = (linear - angular * 0.13 / 2) / 0.017
target_wl = float(np.clip(v_l, -41.2, 41.2))
print(f"target_wl={target_wl:.2f}")

n_sub = int(round(0.08 / m.opt.timestep))
for i in range(n_sub):
    d.ctrl[env._wheel_l_id] = float(np.clip(0.0005 * (target_wl - d.qvel[WHEEL_L_QVEL]), -0.08, 0.08))
    d.ctrl[env._wheel_r_id] = float(np.clip(0.0005 * (target_wl - d.qvel[WHEEL_R_QVEL]), -0.08, 0.08))
    if i < 5 or i == n_sub - 1:
        ncon = d.ncon
        print(f"sub {i}: ctrl={d.ctrl[0]:.5f} wl={d.qvel[WHEEL_L_QVEL]:.3f} wr={d.qvel[WHEEL_R_QVEL]:.3f} "
              f"qfrc_act_l={d.qfrc_actuator[WHEEL_L_QVEL]:.5f} ncon={ncon} "
              f"pos=({d.qpos[0]:.3f},{d.qpos[1]:.3f})")
    mujoco.mj_step(m, d)

# contact inspection
print("\ncontacts after step:")
for i in range(min(d.ncon, 10)):
    c = d.contact[i]
    g1 = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, c.geom1)
    g2 = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, c.geom2)
    print(f"  contact {i}: {g1} <-> {g2} dist={c.dist:.5f}")
print(f"\nfinal: pos=({d.qpos[0]:.4f},{d.qpos[1]:.4f}) wl={d.qvel[WHEEL_L_QVEL]:.3f} wr={d.qvel[WHEEL_R_QVEL]:.3f}")
