#!/usr/bin/env python3
"""Opponent servo test: does the opponent move under FW_MAX? Can the robot push it?"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from simulation.mujoco_env import MuJoCoBottleSumoEnv, Action

# --- test 1: opponent drives forward under a fixed FW_MAX strategy ---
def fw_strategy(obs, step):
    return int(Action.FW_MAX)

env = MuJoCoBottleSumoEnv(seed=1, opponent_strategy=fw_strategy, opponent_strategy_name="fwtest")
obs, _ = env.reset(seed=1)
# robot parked at origin facing opponent? place robot at (0, -0.2) heading 90deg (facing +y where opp is)
env.data.qpos[0:3] = [0.0, -0.2, 0.03]
env.data.qpos[3:7] = [0.7071, 0, 0, 0.7071]  # heading 90deg
env.data.qvel[0:6] = 0.0
env._sync_state()
x0, y0 = env.opponent_x, env.opponent_y
for i in range(25):
    obs, r, term, trunc, info = env.step(int(Action.STOP))
print(f"opponent FW_MAX self-drive: ({x0:.3f},{y0:.3f}) -> ({env.opponent_x:.3f},{env.opponent_y:.3f})  moved={math.hypot(env.opponent_x-x0, env.opponent_y-y0):.3f} m")

# --- test 2: robot pushes a PASSIVE opponent (strategy returns STOP) ---
def stop_strategy(obs, step):
    return int(Action.STOP)

env2 = MuJoCoBottleSumoEnv(seed=2, opponent_strategy=stop_strategy, opponent_strategy_name="stop")
obs, _ = env2.reset(seed=2)
env2.data.qpos[0:3] = [0.0, -0.2, 0.03]
env2.data.qpos[3:7] = [0.7071, 0, 0, 0.7071]
env2.data.qvel[0:6] = 0.0
env2.data.qpos[9:12] = [0.0, 0.02, 0.03]
env2.data.qvel[8:14] = 0.0
env2._sync_state()
x0, y0 = env2.opponent_x, env2.opponent_y
for i in range(25):
    obs, r, term, trunc, info = env2.step(int(Action.FW_MAX))
    if term or trunc:
        print(f"episode ended at step {i}: term={term} trunc={trunc} reward={r}")
        break
print(f"robot push vs STOP opponent: ({x0:.3f},{y0:.3f}) -> ({env2.opponent_x:.3f},{env2.opponent_y:.3f})  pushed={math.hypot(env2.opponent_x-x0, env2.opponent_y-y0):.3f} m")
