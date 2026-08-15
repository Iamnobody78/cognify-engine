#!/usr/bin/env python3
"""Debug opponent force servo per substep."""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import mujoco
from simulation.mujoco_env import MuJoCoBottleSumoEnv, Action, OPP_SERVO_GAIN, OPP_THRUST_MAX

def fw_strategy(obs, step):
    return int(Action.FW_MAX)

env = MuJoCoBottleSumoEnv(seed=1, opponent_strategy=fw_strategy, opponent_strategy_name="fwtest")
obs, _ = env.reset(seed=1)
env.data.qpos[0:3] = [0.0, -0.2, 0.03]
env.data.qpos[3:7] = [0.7071, 0, 0, 0.7071]
env.data.qvel[0:6] = 0.0
env.data.qpos[9:12] = [0.0, 0.0, 0.03]
env.data.qpos[12:16] = [1.0, 0, 0, 0]  # heading 0 -> +x
env.data.qvel[8:14] = 0.0
env._sync_state()
m, d = env.model, env.data
print(f"opp quat: {d.qpos[12:16]} heading: {env.opponent_theta:.3f}")
print(f"qfrc_applied before: {d.qfrc_applied[8:14]}")

# manual step: FW_MAX with substep printing
from simulation.mujoco_env import ACTION_MAP
linear, angular = ACTION_MAP.get(Action.FW_MAX, (0.0, 0.0))
print(f"action FW_MAX -> lin={linear} ang={angular}")
OPP_QVEL = 8
for i in range(8):
    qo = d.qpos[12:16]
    h = math.atan2(2 * (qo[0] * qo[3] + qo[1] * qo[2]), 1 - 2 * (qo[2] ** 2 + qo[3] ** 2))
    err_vx = linear * math.cos(h) - d.qvel[OPP_QVEL + 0]
    err_vy = linear * math.sin(h) - d.qvel[OPP_QVEL + 1]
    d.qfrc_applied[OPP_QVEL + 0] = float(max(min(OPP_SERVO_GAIN * err_vx, OPP_THRUST_MAX), -OPP_THRUST_MAX))
    d.qfrc_applied[OPP_QVEL + 1] = float(max(min(OPP_SERVO_GAIN * err_vy, OPP_THRUST_MAX), -OPP_THRUST_MAX))
    mujoco.mj_step(m, d)
    print(f"sub{i}: h={math.degrees(h):6.1f} F_applied=({d.qfrc_applied[8]:6.2f},{d.qfrc_applied[9]:6.2f}) "
          f"v_opp=({d.qvel[8]:6.3f},{d.qvel[9]:6.3f}) pos=({d.qpos[9]:6.3f},{d.qpos[10]:6.3f})")
