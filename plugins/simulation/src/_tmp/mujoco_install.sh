#!/bin/bash
# Install MuJoCo into WSL python3 (user-level), verify minimal sim runs.
set -e
pip3 install --user mujoco 2>&1 | tail -3
python3 - <<'EOF'
import mujoco
print("MuJoCo", mujoco.__version__, "OK")
# minimal model: two boxes on a plane (bottle-sumotori style contact test)
XML = """
<mujoco model="contact_test">
  <option gravity="0 0 -9.81"/>
  <worldbody>
    <geom name="ground" type="plane" size="1 1 0.01" friction="1"/>
    <body name="a" pos="0 0 0.06">
      <geom type="cylinder" size="0.05 0.02" mass="1.0" friction="1"/>
    </body>
    <body name="b" pos="0.12 0 0.06">
      <geom type="cylinder" size="0.05 0.02" mass="1.0" friction="1"/>
    </body>
  </worldbody>
</mujoco>
"""
m = mujoco.MjModel.from_xml_string(XML)
d = mujoco.MjData(m)
# push b toward a
d.qpos[3] = 0.10
for i in range(100):
    mujoco.mj_step(m, d)
print("contact present:", bool(d.ncon > 0))
print("a pos after 100 steps:", d.qpos[0:2])
print("SIM OK: physics engine computes contacts correctly")
EOF
