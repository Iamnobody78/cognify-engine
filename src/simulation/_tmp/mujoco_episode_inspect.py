#!/usr/bin/env python3
"""Instrument one aggressive episode: robot/opponent positions + engagement."""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from simulation.v9_gate_evaluator import OpponentStrategies
from simulation.mujoco_env import MuJoCoBottleSumoEnv, DOHYO_RADIUS

opp_fn = OpponentStrategies.get("aggressive")
env = MuJoCoBottleSumoEnv(opponent_strategy=opp_fn, opponent_strategy_name="aggressive")

# build a minimal abdl agent like the evaluator
from simulation.v9_gate_evaluator import V9RuleAgent
agent = V9RuleAgent()

obs, _ = env.reset(seed=42)
print(f"start: robot=({env.robot_x:.3f},{env.robot_y:.3f}) th={math.degrees(env.robot_theta):.0f} "
      f"opp=({env.opponent_x:.3f},{env.opponent_y:.3f}) opp_th={math.degrees(env.opponent_theta):.0f}")
for step in range(500):
    a = agent.select_action(obs)
    obs, r, term, trunc, info = env.step(a)
    if step % 25 == 0 or term or trunc:
        rd = math.hypot(env.robot_x, env.robot_y)
        od = math.hypot(env.opponent_x, env.opponent_y)
        print(f"step {step:3d}: act={a:2d} r={r:+8.2f} robot_d={rd:.3f} opp_d={od:.3f} "
              f"opp_ang={math.degrees(obs[5]):6.1f} edge_f={obs[0]:.2f} term={term}")
    if term or trunc:
        print(f"END at {step}: {'WIN' if term and r > 5 else 'LOSS/timeout'}")
        break
