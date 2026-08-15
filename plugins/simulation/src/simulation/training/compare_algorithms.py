"""
compare_algorithms.py — DQN vs TD3 vs SAC benchmark

CLI: python compare_algorithms.py --algo dqn|td3|sac|all --episodes 100
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

import numpy as np

# Path setup
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.resolve()))
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from bottlesumo_pi.simulation.continuous_env import ContinuousBottleSumoEnv
from bottlesumo_pi.simulation.lightweight_env import LightweightBottleSumoEnv
from bottlesumo_pi.common.continuous_agents import (
    TD3Agent, TD3Config,
    SACAgent, SACConfig,
)
from bottlesumo_pi.common.agent import DQNAgent
from bottlesumo_pi.common.config import Config


def scale_action(raw: np.ndarray, env: ContinuousBottleSumoEnv) -> np.ndarray:
    ll, lh = env.ACTION_LINEAR_LOW, env.ACTION_LINEAR_HIGH
    al, ah = env.ACTION_ANGULAR_LOW, env.ACTION_ANGULAR_HIGH
    s = np.zeros(2, np.float32)
    s[0] = (raw[0] + 1) / 2 * (lh - ll) + ll
    s[1] = (raw[1] + 1) / 2 * (ah - al) + al
    return s


def run_dqn(episodes: int, seed: int) -> dict:
    env = LightweightBottleSumoEnv(opponent_profile="aggressive", seed=seed)
    cfg = Config(); cfg.state_dim = 7; cfg.action_dim = 21; cfg.device = "cpu"; cfg.use_double_dqn = True
    agent = DQNAgent(cfg)

    rewards, steps = [], 0
    for ep in range(episodes):
        obs, _ = env.reset(); er = 0.0; done = False; truncated = False
        while not (done or truncated):
            a = agent.select_action(obs, training=True)
            if isinstance(a, np.ndarray): a = int(a.item())
            else: a = int(a)
            obs, r, done, truncated, _ = env.step(a)
            er += r; steps += 1
        rewards.append(er)
    env.close()
    return {"agent": "DQN", "rewards": rewards, "steps": steps, "episodes": episodes}


def run_td3(episodes: int, seed: int) -> dict:
    env = ContinuousBottleSumoEnv(opponent_profile="aggressive", seed=seed)
    cfg = TD3Config(state_dim=7, action_dim=2, max_action=1.0,
                     batch_size=128, buffer_capacity=20000,
                     exploration_noise=0.2, actor_lr=1e-3, critic_lr=1e-3, device="cpu")
    agent = TD3Agent(cfg)

    rewards, steps = [], 0
    for ep in range(episodes):
        obs, _ = env.reset(); er = 0.0; done = False; truncated = False
        while not (done or truncated):
            a = scale_action(agent.select_action(obs, explore=True), env)
            obs, r, done, truncated, _ = env.step(a)
            er += r; steps += 1
        rewards.append(er)
    env.close()
    return {"agent": "TD3", "rewards": rewards, "steps": steps, "episodes": episodes}


def run_sac(episodes: int, seed: int) -> dict:
    env = ContinuousBottleSumoEnv(opponent_profile="aggressive", seed=seed)
    cfg = SACConfig(state_dim=7, action_dim=2, max_action=1.0,
                     batch_size=128, buffer_capacity=20000,
                     alpha=0.2, learn_alpha=True,
                     actor_lr=1e-3, critic_lr=1e-3, alpha_lr=3e-4, device="cpu")
    agent = SACAgent(cfg)

    rewards, steps = [], 0
    for ep in range(episodes):
        obs, _ = env.reset(); er = 0.0; done = False; truncated = False
        while not (done or truncated):
            a = scale_action(agent.select_action(obs, explore=True), env)
            obs, r, done, truncated, _ = env.step(a)
            er += r; steps += 1
        rewards.append(er)
    env.close()
    return {"agent": "SAC", "rewards": rewards, "steps": steps, "episodes": episodes,
            "alpha_final": agent.alpha}


def compute_stats(results: list[dict]) -> dict:
    stats = {}
    for r in results:
        rew = np.array(r["rewards"])
        name = r["agent"]
        stats[name] = {
            "mean": float(np.mean(rew)),
            "std": float(np.std(rew)),
            "median": float(np.median(rew)),
            "min": float(np.min(rew)),
            "max": float(np.max(rew)),
            "win_rate": float(np.mean(rew > 0)),
            "avg_steps": r["steps"] / r["episodes"],
            "episodes": r["episodes"],
        }
        if "alpha_final" in r:
            stats[name]["alpha_final"] = r["alpha_final"]
    return stats


def generate_report(stats: dict, out: Path):
    rows = {"DQN": "DQN (21离散)", "TD3": "TD3 (2连续·确定性)", "SAC": "SAC (2连续·随机)"}
    lines = [f"# DQN vs TD3 vs SAC — 算法基准对比",
             f"\n> {datetime.now().strftime('%Y-%m-%d %H:%M')} | episodes={next(iter(stats.values()))['episodes']}",
             f"\n| 指标 | DQN | TD3 | SAC |",
             f"|------|:--:|:--:|:--:|"]

    d, t, s = stats.get("DQN", {}), stats.get("TD3", {}), stats.get("SAC", {})
    lines.append(f"| 平均奖励 | {d.get('mean',0):.1f} | {t.get('mean',0):.1f} | {s.get('mean',0):.1f} |")
    lines.append(f"| 奖励波动 | {d.get('std',0):.1f} | {t.get('std',0):.1f} | {s.get('std',0):.1f} |")
    lines.append(f"| 中位数 | {d.get('median',0):.1f} | {t.get('median',0):.1f} | {s.get('median',0):.1f} |")
    lines.append(f"| 胜率 | {d.get('win_rate',0):.1%} | {t.get('win_rate',0):.1%} | {s.get('win_rate',0):.1%} |")
    lines.append(f"| 最小/最大 | {d.get('min',0):.0f}/{d.get('max',0):.0f} | {t.get('min',0):.0f}/{t.get('max',0):.0f} | {s.get('min',0):.0f}/{s.get('max',0):.0f} |")
    lines.append(f"| 均步数 | {d.get('avg_steps',0):.0f} | {t.get('avg_steps',0):.0f} | {s.get('avg_steps',0):.0f} |")

    if "alpha_final" in s:
        lines.append(f"\n**SAC 熵温度**: α = {s['alpha_final']:.4f}")

    winner = max(stats, key=lambda k: stats[k]["mean"])
    lines.append(f"\n**胜出**: {rows.get(winner, winner)} (μ={stats[winner]['mean']:.1f})")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport: {out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="DQN vs TD3 vs SAC benchmark")
    p.add_argument("--algo", default="all", choices=["dqn", "td3", "sac", "all"])
    p.add_argument("--episodes", type=int, default=100)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("-o", default="reports/continuous_rl")
    args = p.parse_args()

    print("=" * 60)
    print(f" DQN vs TD3 vs SAC — {args.episodes} episodes")
    print("=" * 60)

    results = []
    algo_map = {"dqn": run_dqn, "td3": run_td3, "sac": run_sac}
    algos = ["dqn", "td3", "sac"] if args.algo == "all" else [args.algo]

    for name in algos:
        print(f"\n[{name.upper()}] running...")
        r = algo_map[name](args.episodes, args.seed)
        rew = np.array(r["rewards"])
        print(f"  {r['agent']}: mean={np.mean(rew):.1f} ± {np.std(rew):.1f}  "
              f"win_rate={np.mean(rew > 0):.1%}  steps={r['steps']}")
        results.append(r)

    stats = compute_stats(results)

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out = Path(args.o) / stamp
    out.mkdir(parents=True, exist_ok=True)

    with open(out / "results.json", "w", encoding="utf-8") as f:
        json.dump({"raw": [[float(v) for v in r["rewards"]] for r in results]}, f, indent=2)
        # Full stats saved separately
        with open(out / "stats.json", "w", encoding="utf-8") as f2:
            json.dump(stats, f2, indent=2)

    generate_report(stats, out / "report.md")
    print(f"\n[OK] saved to {out}")
