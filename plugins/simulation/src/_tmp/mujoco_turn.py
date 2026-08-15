#!/usr/bin/env python3
"""Turn debug: wheel velocities + heading during TURN_L_HARD."""
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
print("robot_theta from env:", env.robot_theta)
q = env.data.qpos[3:7]
print("quat (w,x,y,z):", q, "atan2 from quat:", math.atan2(2*(q[0]*q[3]+q[1]*q[2]), 1-2*(q[2]**2+q[3]**2)))
m = env.model
d = env.data
def dump(step):
    q = d.qpos[3:7]
    th = math.atan2(2*(q[0]*q[3]+q[1]*q[2]), 1-2*(q[2]**2+q[3]**2))
    names = [(mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, c.geom1),
              mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, c.geom2)) for c in d.contact[:d.ncon]]
    print(f"step {step}: z={d.qpos[2]:.4f} tilt=({q[1]:+.4f},{q[2]:+.4f}) th={math.degrees(th):.1f} "
          f"wl={d.qvel[WHEEL_L_QVEL]:.2f} wr={d.qvel[WHEEL_R_QVEL]:.2f} "
          f"ctrl={d.ctrl[0]:.4f}/{d.ctrl[1]:.4f} int={env._int_l:.3f}/{env._int_r:.3f} "
          f"ncon={d.ncon} geoms={names[:6]}")

dump("init")
for i in range(5):
    env.step(int(Action.TURN_L_HARD))
    dump(i)

