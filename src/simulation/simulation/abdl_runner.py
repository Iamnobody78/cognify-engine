#!/usr/bin/env python3
"""
ABDL Runner — Rules-Driven BottleSumo Simulation
=================================================
Uses ABDL rules to control the agent during simulation episodes.
Compares ABDL-driven performance against random agent baseline.

This is P1 validation: proving that the formal ABDL rule language
can drive physics simulation with performance comparable to
hand-coded heuristics.

Usage:
    python simulation/abdl_runner.py --episodes 50
    python simulation/abdl_runner.py --episodes 100 --compare
    python simulation/abdl_runner.py --episodes 10 --verbose
"""
import json
import sys
import time
from pathlib import Path
from collections import defaultdict
from typing import Any

# Path setup
_BASE = Path(__file__).resolve().parent.parent
if str(_BASE) not in sys.path:
    sys.path.insert(0, str(_BASE))

import numpy as np
from simulation.lightweight_env import LightweightBottleSumoEnv
from simulation.wheel_to_discrete import Action, SAFE_ACTIONS_WHEN_EDGE_CLOSE
from core.meta_language.abdl_action_bridge import ABDLDecisionMaker


# ── Agent Strategies ─────────────────────────────────────────────────────────

class RandomAgent:
    """Baseline: random action selection with edge safety."""

    def __init__(self):
        self.action_space = 21

    def select_action(self, obs: np.ndarray, info: dict = None) -> int:
        return np.random.randint(0, self.action_space)

    def reset(self):
        pass

    def name(self) -> str:
        return "RandomAgent"


class HeuristicAgent:
    """Hand-coded heuristic: pursue opponent, avoid edge."""

    def __init__(self):
        self._prev_pos = None
        self._stuck = 0

    def select_action(self, obs: np.ndarray, info: dict = None) -> int:
        # Parse 7-dim observation
        # [edge_front, edge_back, edge_left, edge_right, opp_dist, opp_angle, robot_speed]
        edge_f = float(obs[0])
        edge_l = float(obs[2])
        edge_r = float(obs[3])
        opp_dist = float(obs[4])
        opp_angle = float(obs[5])
        speed = float(obs[6])

        # Edge safety: check all 4 edge sensors (1=ok, 0=on edge)
        min_edge = min(edge_f, obs[1], edge_l, edge_r)
        if min_edge < 0.3:
            return Action.REV_SLOW.value
        if min_edge < 0.5:
            return Action.CREEP_FWD.value

        # Face and pursue opponent
        if opp_dist > 3.9:  # No opponent in range
            return Action.TURN_L_MILD.value if speed > 0.1 else Action.FW_SLOW.value

        abs_angle = abs(opp_angle)
        if abs_angle < 15:
            if opp_dist < 0.5:
                return Action.FW_MAX.value
            elif opp_dist < 1.0:
                return Action.FW_FAST.value
            return Action.FW_MED.value
        elif abs_angle < 45:
            if opp_dist < 0.5:
                return Action.FW_FAST.value
            return Action.FW_MED.value
        elif opp_angle > 0:
            return Action.TURN_R_MILD.value
        else:
            return Action.TURN_L_MILD.value

    def reset(self):
        self._prev_pos = None
        self._stuck = 0

    def name(self) -> str:
        return "HeuristicAgent"


class ABDLAgent:
    """ABDL rules-driven agent: uses ABDLDecisionMaker."""

    def __init__(self):
        self.maker = ABDLDecisionMaker()

    def select_action(self, obs: np.ndarray, info: dict = None) -> int:
        world_state = self.maker.builder.build(obs, info)
        return self.maker.decide(world_state)

    def reset(self):
        self.maker.reset()

    def name(self) -> str:
        return "ABDLAgent"


# ── Episode Runner ───────────────────────────────────────────────────────────

def run_episode(env, agent, max_steps: int = 500, verbose: bool = False) -> dict:
    """Run a single episode and return metrics."""
    obs, info = env.reset()
    agent.reset()

    total_reward = 0.0
    steps = 0
    win = False
    crash = False
    actions_used = defaultdict(int)

    for step in range(max_steps):
        action = agent.select_action(obs, info)
        actions_used[int(action)] += 1

        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += float(reward)
        steps += 1

        if verbose and step % 50 == 0:
            print(f"    Step {step}: action={action}, reward={reward:.3f}, "
                  f"obs=[{obs[0]:.2f}, {obs[1]:.2f}, {obs[2]:.2f}, {obs[3]:.2f}]")

        if terminated or truncated:
            break

    # Determine outcome
    if info.get("success", False):
        win = True
    if info.get("crash", False) or reward < -5:
        crash = True

    env.close()

    return {
        "reward": total_reward,
        "steps": steps,
        "win": win,
        "crash": crash,
        "actions_used": dict(actions_used),
    }


# ── Comparison Runner ────────────────────────────────────────────────────────

def run_benchmark(episodes: int = 50, verbose: bool = False) -> dict:
    """Run ABDL agent vs baselines and return comparison."""
    agents = [
        RandomAgent(),
        HeuristicAgent(),
        ABDLAgent(),
    ]

    results = {}

    for agent in agents:
        print(f"\n{'='*60}")
        print(f"Testing: {agent.name()}")
        print(f"{'='*60}")

        episode_results = []
        wins = 0
        crashes = 0
        total_reward = 0.0
        total_steps = 0

        start_time = time.time()

        for ep in range(episodes):
            env = LightweightBottleSumoEnv()
            result = run_episode(env, agent, verbose=(verbose and ep < 3))
            episode_results.append(result)

            if result["win"]:
                wins += 1
            if result["crash"]:
                crashes += 1
            total_reward += result["reward"]
            total_steps += result["steps"]

            if (ep + 1) % 10 == 0:
                elapsed = time.time() - start_time
                wr = wins / (ep + 1) * 100
                print(f"  Episode {ep + 1}/{episodes}: "
                      f"win_rate={wr:.1f}%, "
                      f"avg_reward={total_reward / (ep + 1):.2f}, "
                      f"crashes={crashes}, "
                      f"fps={total_steps / max(elapsed, 0.01):.0f}")

        elapsed = time.time() - start_time
        wr = wins / episodes * 100
        cr = crashes / episodes * 100
        avg_reward = total_reward / episodes
        fps = total_steps / max(elapsed, 0.01)

        # Action distribution
        all_actions = defaultdict(int)
        for r in episode_results:
            for a, c in r["actions_used"].items():
                all_actions[int(a)] += c

        results[agent.name()] = {
            "episodes": episodes,
            "wins": wins,
            "win_rate": round(wr, 1),
            "crashes": crashes,
            "crash_rate": round(cr, 1),
            "avg_reward": round(avg_reward, 3),
            "total_steps": total_steps,
            "elapsed": round(elapsed, 1),
            "fps": round(fps, 0),
            "top_actions": sorted(all_actions.items(), key=lambda x: -x[1])[:5],
        }

        print(f"  Summary: win_rate={wr:.1f}%, avg_reward={avg_reward:.3f}, "
              f"crashes={crashes}, fps={fps:.0f}")

    return results


# ── Report Generator ────────────────────────────────────────────────────────

def print_comparison(results: dict):
    """Print a formatted comparison report."""
    print(f"\n{'='*70}")
    print(f"ABDL Validation Report — BottleSumo P1")
    print(f"{'='*70}\n")

    header = f"{'Agent':20s} {'Win%':>8s} {'Crashes':>8s} {'AvgRew':>10s} {'FPS':>8s}"
    sep = "-" * len(header)
    print(header)
    print(sep)

    bl_agent = None
    for name, r in results.items():
        print(f"{name:20s} {r['win_rate']:>7.1f}% {r['crashes']:>7d}  "
              f"{r['avg_reward']:>9.3f} {r['fps']:>7.0f}")
        if "Random" in name:
            bl_agent = r

    print()

    # Comparison against random baseline
    if bl_agent:
        for name, r in results.items():
            if "Random" in name:
                continue
            wr_ratio = r["win_rate"] / max(bl_agent["win_rate"], 0.01)
            threshold = 0.8  # 80% target
            status = "PASS" if wr_ratio >= threshold else "FAIL"
            print(f"  {name} vs Random: win_rate_ratio={wr_ratio:.2f}x "
                  f"(target: {threshold}x) -> {status}")

    # ABDL vs Heuristic
    abdl = results.get("ABDLAgent", {})
    heur = results.get("HeuristicAgent", {})
    if abdl and heur:
        ratio = abdl["win_rate"] / max(heur["win_rate"], 0.01)
        print(f"  ABDL vs Heuristic: win_rate_ratio={ratio:.2f}x")

    print(f"\n{'='*70}")
    print(f"ABDL Rules active: check simulation_rules.abdl for full rule set")
    print(f"Rule levels: L0(Safety)=3, L1(Tactics)=3, L2(Advanced)=3, L3(Heuristic)=4")
    print(f"{'='*70}")


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="ABDL Validation Runner — P1 BottleSumo"
    )
    parser.add_argument("--episodes", "-e", type=int, default=50,
                        help="Number of episodes per agent")
    parser.add_argument("--compare", "-c", action="store_true", default=True,
                        help="Run all agents for comparison")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose output for first 3 episodes")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="Save results to JSON file")

    args = parser.parse_args()

    print(f"\nABDL P1 Validation — {args.episodes} episodes per agent")
    print(f"{'='*60}")

    results = run_benchmark(args.episodes, verbose=args.verbose)
    print_comparison(results)

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        print(f"\nResults saved to: {out_path}")

    # Save to default location
    default_out = _BASE / ".aionui" / "evolution" / "abdl_validation_results.json"
    default_out.parent.mkdir(parents=True, exist_ok=True)
    default_out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"Results also saved to: {default_out}")
