#!/usr/bin/env python3
"""Isolation: wheel spin in air vs on ground. Measure constraint torque."""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import mujoco
from simulation.mujoco_env import MuJoCoBottleSumoEnv, Action, WHEEL_L_QVEL, WHEEL_R_QVEL

def spin_test(label, lift_robot):
    env = MuJoCoBottleSumoEnv(seed=42)
    obs, _ = env.reset(seed=42)
    env.data.qpos[9:12] = [-0.3, -0.2, 0.03]
    env.data.qvel[8:14] = 0.0
    env.data.qpos[12:16] = [1.0, 0, 0, 0]
    if lift_robot:
        env.data.qpos[2] = 0.10  # robot body up 10cm -> wheels in air
    env._sync_state()
    m, d = env.model, env.data
    # direct torque on wheel_l only, keep wheel_r free
    d.ctrl[0] = 0.25
    d.ctrl[1] = 0.0
    for i in range(5):
        mujoco.mj_step(m, d)
        qc_l = d.qfrc_constraint[WHEEL_L_QVEL]
        print(f"  sub{i}: wl={d.qvel[WHEEL_L_QVEL]:8.3f} wr={d.qvel[WHEEL_R_QVEL]:8.3f} "
              f"qc_l={qc_l:8.4f} qfrc_act_l={d.qfrc_actuator[WHEEL_L_QVEL]:.4f} "
              f"ncon={d.ncon} z={d.qpos[2]:.4f}")
    print()

print("=== wheels ON GROUND (full weight) ===")
spin_test("ground", False)
print("=== wheels IN AIR (robot lifted) ===")
spin_test("air", True)
