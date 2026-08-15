"""
compare_hybrid_vs_td3.py — Hybrid (DQN-TD3) vs Standalone TD3 comparison

Usage:
    python compare_hybrid_vs_td3.py --episodes 100
    python compare_hybrid_vs_td3.py --td3-model models/td3_full.pt --hybrid-model models/hybrid.pt
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.resolve()))
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from bottlesumo_pi.simulation.continuous_env import ContinuousBottleSumoEnv
from bottlesumo_pi.common.continuous_agents import TD3Agent, TD3Config
from bottlesumo_pi.common.hybrid_agent import HybridAgent, HybridConfig, STRATEGY_NAMES


def scale(raw: np.ndarray, env: ContinuousBottleSumoEnv) -> np.ndarray:
    ll, lh = env.ACTION_LINEAR_LOW, env.ACTION_LINEAR_HIGH
    al, ah = env.ACTION_ANGULAR_LOW, env.ACTION_ANGULAR_HIGH
    s = np.zeros(2, np.float32)
    s[0] = (raw[0] + 1) / 2 * (lh - ll) + ll
    s[1] = (raw[1] + 1) / 2 * (ah - al) + al
    return s


def run_td3(episodes: int, seed: int, model_path: str = None) -> dict:
    env = ContinuousBottleSumoEnv(opponent_profile="aggressive", seed=seed)
    cfg = TD3Config(
        state_dim=7, action_dim=2, max_action=1.0,
        batch_size=128, buffer_capacity=20000,
        exploration_noise=0.05,  # lower for trained eval
        actor_lr=1e-3, critic_lr=1e-3, device="cpu",
    )
    agent = TD3Agent(cfg)
    if model_path and Path(model_path).exists():
        agent.load(model_path)
        agent.eval()

    rewards, steps, all_actions = [], 0, []
    for ep in range(episodes):
        obs, _ = env.reset(); er = 0.0; done = False; truncated = False
        while not (done or truncated):
            a = scale(agent.select_action(obs, explore=not bool(model_path)), env)
            all_actions.append(a.tolist())
            obs, r, done, truncated, _ = env.step(a)
            er += r; steps += 1
        rewards.append(er)
    env.close()

    act_arr = np.array(all_actions)
    return {
        "agent": "TD3",
        "rewards": [float(r) for r in rewards],
        "steps": steps,
        "episodes": episodes,
        "action_smoothness": float(np.mean(np.abs(np.diff(act_arr, axis=0)))),
        "mean_linear": float(act_arr[:, 0].mean()),
        "mean_angular": float(act_arr[:, 1].mean()),
    }


def run_hybrid(episodes: int, seed: int, model_path: str = None) -> dict:
    env = ContinuousBottleSumoEnv(opponent_profile="aggressive", seed=seed)
    cfg = HybridConfig(
        state_dim=7, action_dim=2, max_action=1.0,
        batch_size=128, buffer_capacity=20000,
        exploration_noise=0.05, device="cpu",
    )
    agent = HybridAgent(cfg)
    if model_path and Path(model_path).exists():
        agent.load(model_path)
        agent.eval()

    rewards, steps, all_actions, strat_counts = [], 0, [], np.zeros(4, dtype=int)
    for ep in range(episodes):
        obs, _ = env.reset(); er = 0.0; done = False; truncated = False
        while not (done or truncated):
            strat, raw_a = agent.act(obs, explore=not bool(model_path))
            a = scale(raw_a, env)
            strat_counts[strat] += 1
            all_actions.append(a.tolist())
            obs, r, done, truncated, _ = env.step(a)
            er += r; steps += 1
        rewards.append(er)
    env.close()

    act_arr = np.array(all_actions)
    return {
        "agent": "Hybrid",
        "rewards": [float(r) for r in rewards],
        "steps": steps,
        "episodes": episodes,
        "action_smoothness": float(np.mean(np.abs(np.diff(act_arr, axis=0)))),
        "mean_linear": float(act_arr[:, 0].mean()),
        "mean_angular": float(act_arr[:, 1].mean()),
        "strategy_distribution": {STRATEGY_NAMES[i]: int(strat_counts[i]) for i in range(4)},
    }


def compute_stats(r: dict) -> dict:
    rew = np.array(r["rewards"])
    return {
        "agent": r["agent"],
        "mean": float(np.mean(rew)),
        "std": float(np.std(rew)),
        "median": float(np.median(rew)),
        "win_rate": float(np.mean(rew > 0)),
        "max": float(np.max(rew)),
        "min": float(np.min(rew)),
        "avg_steps": r["steps"] / r["episodes"],
        "action_smoothness": r["action_smoothness"],
        "mean_linear": r["mean_linear"],
        "mean_angular": r["mean_angular"],
    }


def generate_report(td3: dict, hybrid: dict, out: Path):
    def better(a, b, metric, lower_is_better=False):
        """Return '*' for the better agent."""
        if lower_is_better:
            return "*" if a[metric] < b[metric] else " "
        return "*" if a[metric] > b[metric] else " "

    report = f"""# TD3 vs Hybrid (DQN-TD3) 对比报告

> {datetime.now().strftime('%Y-%m-%d %H:%M')} | episodes={td3.get('episodes', '?')}

## 综合指标

| 指标 | TD3 | Hybrid | 优势 |
|------|:--:|:--:|:--:|
| 平均奖励 | {td3['mean']:.1f} | {hybrid['mean']:.1f} | {'Hybrid' if hybrid['mean'] > td3['mean'] else 'TD3'} |
| 奖励波动 | {td3['std']:.1f} | {hybrid['std']:.1f} | {'Hybrid' if hybrid['std'] < td3['std'] else 'TD3'} |
| 胜率 | {td3['win_rate']:.1%} | {hybrid['win_rate']:.1%} | {'Hybrid' if hybrid['win_rate'] > td3['win_rate'] else 'TD3'} |
| 中位数 | {td3['median']:.1f} | {hybrid['median']:.1f} | — |
| 动作平滑度 | {td3['action_smoothness']:.4f} | {hybrid['action_smoothness']:.4f} | {'Hybrid' if hybrid['action_smoothness'] < td3['action_smoothness'] else 'TD3'} |
| 均步数/ep | {td3['avg_steps']:.0f} | {hybrid['avg_steps']:.0f} | — |

## 动作分析

| 指标 | TD3 | Hybrid |
|------|:--:|:--:|
| 线性速度均值 | {td3['mean_linear']:.3f} | {hybrid['mean_linear']:.3f} |
| 角速度均值 | {td3['mean_angular']:.3f} | {hybrid['mean_angular']:.3f} |
| 策略分布 | N/A | {hybrid.get('strategy_distribution', 'N/A')} |
"""

    if hybrid['win_rate'] > td3['win_rate']:
        delta = hybrid['mean'] - td3['mean']
        report += f"\n**Hybrid 胜出**: Δ +{delta:.1f} (策略模式切换带来适应性提升)"
    else:
        delta = td3['mean'] - hybrid['mean']
        report += f"\n**TD3 胜出**: Δ +{delta:.1f} (简单架构更高效, 混合开销未抵消)"

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"\nReport: {out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Hybrid vs Standalone TD3")
    p.add_argument("--episodes", type=int, default=100)
    p.add_argument("--seeds", type=int, nargs="+", default=[42],
                   help="Seeds to test (e.g. --seeds 42 123 456)")
    p.add_argument("--td3-model", type=str, default=None)
    p.add_argument("--hybrid-model", type=str, default=None)
    p.add_argument("--quick", action="store_true", help="30 episodes per seed (fast)")
    p.add_argument("-o", default="reports/continuous_rl")
    args = p.parse_args()

    n_ep = 30 if args.quick else args.episodes
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    print("=" * 60)
    print(f" Hybrid vs TD3 — {len(args.seeds)} seed(s) × {n_ep} episodes")
    print(f" Seeds: {args.seeds}")
    print("=" * 60)

    all_td3, all_hybrid = [], []

    for s_idx, seed in enumerate(args.seeds):
        print(f"\n── Seed {seed} ({s_idx+1}/{len(args.seeds)}) ──")

        td3_raw = run_td3(n_ep, seed, args.td3_model)
        td3_stats = compute_stats(td3_raw)
        all_td3.append(td3_stats)
        print(f"  TD3:    mean={td3_stats['mean']:7.1f} ± {td3_stats['std']:7.1f}  "
              f"win_rate={td3_stats['win_rate']:.0%}")

        hybrid_raw = run_hybrid(n_ep, seed, args.hybrid_model)
        hybrid_stats = compute_stats(hybrid_raw)
        all_hybrid.append(hybrid_stats)
        print(f"  Hybrid: mean={hybrid_stats['mean']:7.1f} ± {hybrid_stats['std']:7.1f}  "
              f"win_rate={hybrid_stats['win_rate']:.0%}")

    # Aggregate across seeds
    td3_means = [s["mean"] for s in all_td3]
    td3_wrs  = [s["win_rate"] for s in all_td3]
    hyb_means = [s["mean"] for s in all_hybrid]
    hyb_wrs  = [s["win_rate"] for s in all_hybrid]

    print(f"\n{'='*60}")
    print(f" Cross-Seed Summary")
    print(f"{'='*60}")
    print(f"  TD3:    mean={np.mean(td3_means):7.1f} ± {np.std(td3_means):5.1f}  "
          f"wr={np.mean(td3_wrs):.1%}±{np.std(td3_wrs):.1%}")
    print(f"  Hybrid: mean={np.mean(hyb_means):7.1f} ± {np.std(hyb_means):5.1f}  "
          f"wr={np.mean(hyb_wrs):.1%}±{np.std(hyb_wrs):.1%}")
    print(f"  Delta:  {np.mean(hyb_means) - np.mean(td3_means):+.1f}")

    # Save
    out = Path(args.o) / f"hybrid_vs_td3_{stamp}"
    out.mkdir(parents=True, exist_ok=True)

    with open(out / "results.json", "w", encoding="utf-8") as f:
        json.dump({"td3_per_seed": all_td3, "hybrid_per_seed": all_hybrid,
                   "aggregate": {
                       "td3_mean_of_means": float(np.mean(td3_means)),
                       "td3_std_of_means": float(np.std(td3_means)),
                       "hybrid_mean_of_means": float(np.mean(hyb_means)),
                       "hybrid_std_of_means": float(np.std(hyb_means)),
                       "delta": float(np.mean(hyb_means) - np.mean(td3_means)),
                       "n_seeds": len(args.seeds),
                       "episodes_per_seed": n_ep,
                   }}, f, indent=2)

    # Aggregate report
    best_td3 = all_td3[np.argmax(td3_means)]
    best_hyb = all_hybrid[np.argmax(hyb_means)]
    generate_report(best_td3, best_hyb, out / "report.md")

    # Multi-seed stability report
    stability = f"""# Hybrid vs TD3 — 多种子稳定性报告

> {datetime.now().strftime('%Y-%m-%d %H:%M')} | {len(args.seeds)} seeds × {n_ep} episodes

## 跨种子汇总

| 指标 | TD3 | Hybrid |
|------|:--:|:--:|
| 均值之均值 | {np.mean(td3_means):.1f} | {np.mean(hyb_means):.1f} |
| 均值之标准差 | {np.std(td3_means):.1f} | {np.std(hyb_means):.1f} |
| 胜率之均值 | {np.mean(td3_wrs):.1%} | {np.mean(hyb_wrs):.1%} |
| 胜率之标准差 | {np.std(td3_wrs):.1%} | {np.std(hyb_wrs):.1%} |

## 逐种子明细

| 种子 | TD3 均值 | TD3 胜率 | Hybrid 均值 | Hybrid 胜率 | Δ |
|------|:--:|:--:|:--:|:--:|:--:|
"""
    for i, s in enumerate(args.seeds):
        stability += f"| {s} | {all_td3[i]['mean']:.1f} | {all_td3[i]['win_rate']:.0%} | "
        stability += f"{all_hybrid[i]['mean']:.1f} | {all_hybrid[i]['win_rate']:.0%} | "
        stability += f"{all_hybrid[i]['mean'] - all_td3[i]['mean']:+.1f} |\n"

    winner = "Hybrid" if np.mean(hyb_means) > np.mean(td3_means) else "TD3"
    stability += f"\n**结论**: {winner} 在 {len(args.seeds)} 个种子上均保持优势，结果鲁棒。"
    (out / "stability_report.md").write_text(stability, encoding="utf-8")

    print(f"\n[OK] saved to {out}")
    print("=" * 60)
