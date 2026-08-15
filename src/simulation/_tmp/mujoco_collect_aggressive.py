"""
mujoco_collect_aggressive.py — MuJoCo trajectory collection vs aggressive opponent
====================================================================================
Queue #4 (plan C track B): collect rollouts from the MuJoCo backend so we can
analyze *why* abdl gets only 40% there (push failures / lag / edge behavior)
before tuning rules or training a student policy.

Output: models/mujoco_aggressive_trajectories/ep_XXXXXX.json
  {ep: int, backend: "mujoco", opponent: "aggressive", agent: str,
   steps: int, won: bool, reason: str,
   trajectory: [{obs: [7], action: int, reward: float, opp_strategy: str}, ...]}

Usage (WSL):
  python3 _tmp/mujoco_collect_aggressive.py --agent abdl --episodes 500 --out models/mujoco_aggressive_trajectories
  python3 _tmp/mujoco_collect_aggressive.py --agent abdl --episodes 5 --dry-run   # smoke test
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from simulation.v9_gate_evaluator import V9RuleAgent
from simulation.mujoco_env import MuJoCoBottleSumoEnv


def collect(agent_name: str, episodes: int, out_dir: Path, dry_run: bool) -> None:
    env = MuJoCoBottleSumoEnv(opponent_profile="aggressive",
                              opponent_strategy_name="aggressive", render_mode="none")
    agent = V9RuleAgent(force_heuristic=(agent_name == "heuristic"))

    # map agent_name → what select_action_traced does for the *named* agents
    # (abdl uses ABDL rules; heuristic forced; v11 uses ABDL+improved params)
    if agent_name not in ("abdl", "heuristic", "v11"):
        raise SystemExit(f"unknown agent: {agent_name}")

    summary = {"agent": agent_name, "episodes": 0, "wins": 0, "pushes": 0,
               "timeouts": 0, "out_of_bounds": 0}
    per_rule = {}

    for ep in range(episodes):
        obs, _ = env.reset(seed=1000 + ep)
        ep_data = {"ep": ep, "backend": "mujoco", "opponent": "aggressive",
                   "agent": agent_name, "steps": 0, "won": False, "reason": "timeout",
                   "trajectory": []}
        total_r = 0.0
        for step in range(500):
            action, trace = agent.select_action_traced(list(obs))
            obs2, reward, terminated, truncated, info = env.step(action)
            total_r += float(reward)
            # compact trace: rule fired (or heuristic branch) + sensor context
            decision = trace.get("rule_id") or trace.get("branch") or "?"
            ep_data["trajectory"].append({
                "obs": [round(float(x), 4) for x in obs],
                "action": int(action),
                "reward": round(float(reward), 4),
                "decision": decision,
                "mode": trace.get("mode"),
                "opp_dist": round(float(obs[4]), 4),
                "opp_angle_deg": round(float(obs[5]), 4),
            })
            per_rule[decision] = per_rule.get(decision, 0) + 1
            obs = obs2
            ep_data["steps"] = step + 1
            if terminated or truncated:
                ep_data["won"] = bool(terminated and total_r > 5.0)
                info_r = info or {}
                if isinstance(info_r, dict) and info_r.get("result"):
                    ep_data["reason"] = str(info_r.get("result"))
                elif terminated:
                    ep_data["reason"] = "win" if ep_data["won"] else "terminated"
                else:
                    ep_data["reason"] = "timeout"
                break
        summary["episodes"] += 1
        if ep_data["won"]:
            summary["wins"] += 1
        if ep_data["reason"] == "timeout":
            summary["timeouts"] += 1
        if "out" in ep_data["reason"] or "edge" in ep_data["reason"]:
            summary["out_of_bounds"] += 1

        if dry_run:
            print(f"[dry] ep={ep} steps={ep_data['steps']} r={total_r:+.1f} "
                  f"won={ep_data['won']} reason={ep_data['reason']} "
                  f"decisions={sorted(set(d['decision'] for d in ep_data['trajectory']))[:6]}")
            continue

        out_dir.mkdir(parents=True, exist_ok=True)
        with (out_dir / f"ep_{ep:06d}.json").open("w") as f:
            json.dump(ep_data, f)

    winrate = (summary["wins"] / summary["episodes"]) * 100 if summary["episodes"] else 0.0
    print(f"\n===== MuJoCo aggressive collection: agent={agent_name} =====")
    print(f"episodes={summary['episodes']} wins={summary['wins']} "
          f"winrate={winrate:.1f}% timeouts={summary['timeouts']} "
          f"oob={summary['out_of_bounds']}")
    top = sorted(per_rule.items(), key=lambda kv: -kv[1])[:10]
    print("top decisions fired:", {k: v for k, v in top})
    return winrate


def main():
    ap = argparse.ArgumentParser(description="MuJoCo aggressive trajectory collection")
    ap.add_argument("--agent", default="abdl", choices=["abdl", "heuristic", "v11"])
    ap.add_argument("--episodes", type=int, default=500)
    ap.add_argument("--out", default="models/mujoco_aggressive_trajectories")
    ap.add_argument("--dry-run", action="store_true", help="smoke test without writing files")
    args = ap.parse_args()
    collect(args.agent, args.episodes, Path(args.out), args.dry_run)


if __name__ == "__main__":
    main()
