"""Verify sentinel: same V9RuleAgent instance should print INFO only once."""
import sys, io, os
sys.path.insert(0, ".")
from simulation.v9_gate_evaluator import V9RuleAgent

a = V9RuleAgent(force_heuristic=True)
obs = [0.5, 0.5, 0.5, 0.5, 1.0, 0.0, 0.1, 0.0, 0.0]
buf = io.StringIO()
old = sys.stderr
sys.stderr = buf
for i in range(5):
    a.select_action(obs)
sys.stderr = old
n = buf.getvalue().count("INFO: --agent heuristic")
print(f"select_action x5, INFO prints = {n} (expect 1)")
assert n == 1, f"sentinel broken: {n} prints"
print("SENTINEL OK")
