"""Verify BETWEEN-condition parsing bug in ABDL engine (queue #4 root cause)."""
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.meta_language.abdl_engine import ConditionEvaluator

# world state mimicking mid-arena pose, opponent close & aligned:
# edge_prox = 0.2 (safe), opp_dist = 0.15, opp_angle = 5 deg
ws = {
    "sensors": {"edge_proximity": 0.2, "opponent_dist": 0.15,
                "opponent_angle": 5.0, "opponent_found": True,
                "stuck_counter": 0, "push_force": 2.0, "agent_speed": 0.3,
                "steps_remaining": 400},
    "metrics": {"opponent_angle": 5.0, "opponent_dist": 0.15},
    "state": {},
    "config": {},
    "entities": [],
}

ev = ConditionEvaluator(ws)

# The exact conditions as written in simulation_rules.abdl (FIXED form):
tests = {
    "OPPONENT-FOUND (should trigger, safe zone)":
        "EXISTS(opponent_found) AND sensor(opponent_found) == True AND sensor(edge_proximity) < 0.5",
    "CLOSE-PUSH (BETWEEN-first form, fixed)":
        "sensor(opponent_dist) < 0.22 AND BETWEEN(sensor(opponent_angle), -12, 12) AND sensor(edge_proximity) < 0.4",
    "CAUTIOUS-EDGE (BETWEEN-first form, fixed)":
        "BETWEEN(sensor(edge_proximity), 0.4, 0.6)",
    "LOST-NEAR-EDGE (BETWEEN-first form, fixed)":
        "EXISTS(opponent_found) AND sensor(opponent_found) == False AND BETWEEN(sensor(edge_proximity), 0.3, 0.6)",
    "CAUTIOUS-EDGE mid-zone (edge_prox=0.5, should trigger)":
        None,  # replaced below
}

tests.pop("CAUTIOUS-EDGE mid-zone (edge_prox=0.5, should trigger)")

for name, cond in tests.items():
    ok, reason = ev.evaluate(cond)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    print(f"      -> {reason[:110]}")

# zone boundary check: CAUTIOUS-EDGE must trigger when edge_prox=0.5
ev2 = ConditionEvaluator({
    "sensors": {"edge_proximity": 0.5, "opponent_found": False,
                "opponent_dist": 2.0, "opponent_angle": 0.0},
    "metrics": {}, "state": {}, "config": {}, "entities": [],
})
ok, reason = ev2.evaluate(
    "BETWEEN(sensor(edge_proximity), 0.4, 0.6)")
print(f"[{'PASS' if ok else 'FAIL'}] CAUTIOUS-EDGE at edge_prox=0.5 (mid dead-zone)")
print(f"      -> {reason[:110]}")
