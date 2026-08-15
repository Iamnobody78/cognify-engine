#!/usr/bin/env python3
"""Run the V9 gate on the mujoco backend and print a compact summary."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from simulation.v9_gate_evaluator import V9GateEvaluator

agent_name = sys.argv[1] if len(sys.argv) > 1 else "abdl"
evaluator = V9GateEvaluator(episodes=10, backend="mujoco")
report = evaluator.evaluate(agent_name=agent_name)
print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
