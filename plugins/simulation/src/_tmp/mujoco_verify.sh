#!/bin/bash
# MuJoCo minimal contact verification (fixed: free joints)
python3 - <<'EOF'
import mujoco
print("MuJoCo", mujoco.__version__, "OK")
XML = """
<mujoco model="contact_test">
  <option gravity="0 0 -9.81"/>
  <worldbody>
    <geom name="ground" type="plane" size="1 1 0.01" friction="1"/>
    <body name="a" pos="0 0 0.06">
      <joint type="free"/>
      <geom type="cylinder" size="0.05 0.02" mass="1.0" friction="1"/>
    </body>
    <body name="b" pos="0.12 0 0.06">
      <joint type="free"/>
      <geom type="cylinder" size="0.05 0.02" mass="1.0" friction="1"/>
    </body>
  </worldbody>
</mujoco>
"""
m = mujoco.MjModel.from_xml_string(XML)
d = mujoco.MjData(m)
# push b toward a (qpos: a xyz=0:3, a quat=3:7, b xyz=7:10)
d.qpos[7] = 0.10
for i in range(300):
    mujoco.mj_step(m, d)
print("contacts:", d.ncon, "| a pos:", [round(v,3) for v in d.qpos[0:2]], "| b pos:", [round(v,3) for v in d.qpos[7:9]])
print("SIM OK: contact physics computes")
EOF
