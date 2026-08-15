#!/usr/bin/env python3
"""Print actual contact friction for the opponent."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import mujoco
from simulation.mujoco_env import MuJoCoBottleSumoEnv

env = MuJoCoBottleSumoEnv(seed=1)
obs, _ = env.reset(seed=1)
m, d = env.model, env.data
print("geom frictions:")
for i in range(m.ngeom):
    g = m.geom(i)
    print(f"  id={i} name={mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, i)} friction={g.friction}")
print("\ncontacts after a step:")
env.step(0)
for i in range(d.ncon):
    c = d.contact[i]
    n1 = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, c.geom1) or f"g{c.geom1}"
    n2 = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, c.geom2) or f"g{c.geom2}"
    print(f"  {i}: {n1} <-> {n2} friction={c.friction} dist={c.dist:.6f}")
# normal force per contact
print("\nnormal forces (cforce z of contacts):")
for i in range(d.ncon):
    print(f"  {i}: F=({d.cforce[i][0]:.2f},{d.cforce[i][1]:.2f},{d.cforce[i][2]:.2f})")
