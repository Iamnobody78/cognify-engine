#!/usr/bin/env python3
"""Deep contact inspection during TURN_L_HARD."""
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
m = env.model
d = env.data

# geom info
print("geoms:")
for i in range(m.ngeom):
    g = m.geom(i)
    print(f"  id={i} name={mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, i)} "
          f"body={mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, g.bodyid)} "
          f"friction={g.friction[0]:.3f}/{g.friction[1]:.4f}/{g.friction[2]:.5f}")
print("actuators:", [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_ACTUATOR, i) for i in range(m.nu)])

env.step(int(Action.TURN_L_HARD))
print(f"\nwl={d.qvel[WHEEL_L_QVEL]:.3f} wr={d.qvel[WHEEL_R_QVEL]:.3f} ctrl={d.ctrl[0]:.4f}/{d.ctrl[1]:.4f}")
print("contacts (geom1 -> geom2, dist, friction):")
for i in range(d.ncon):
    c = d.contact[i]
    n1 = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, c.geom1) or f"g{c.geom1}"
    n2 = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, c.geom2) or f"g{c.geom2}"
    print(f"  {i}: {n1} <-> {n2}  dist={c.dist:.6f}  mu={c.friction[0]:.3f}")
print("contact forces (ncon=%d):" % d.ncon)
for i in range(d.ncon):
    c = d.cforce[i]
    print(f"  {i}: F=({c[0]:8.2f},{c[1]:8.2f},{c[2]:8.2f}) T=({c[3]:7.3f},{c[4]:7.3f},{c[5]:7.3f})")
print(f"qfrc_actuator wheels: {d.qfrc_actuator[WHEEL_L_QVEL]:.4f} {d.qfrc_actuator[WHEEL_R_QVEL]:.4f}")
print(f"qfrc_constraint wheels: {d.qfrc_constraint[WHEEL_L_QVEL]:.4f} {d.qfrc_constraint[WHEEL_R_QVEL]:.4f}")
