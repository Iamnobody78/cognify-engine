#!/usr/bin/env python3
"""
ablate_dqn_vs_ddqn.py — DQN vs DDQN 消融实验框架 (v11.15)

Usage:
    python simulation/training/ablate_dqn_vs_ddqn.py --runs 3 --episodes 500
    python simulation/training/ablate_dqn_vs_ddqn.py --seeds 42 123 456 --episodes 1000 -v

Output:
    reports/ablation/dqn_vs_ddqn_YYYY-MM-DD_HHMMSS/
    ├── raw_results.json           # 原始训练数据
    ├── comparison_report.md       # Markdown 对比报告
    ├── reward_curves.png          # 分图 DQN/DDQN
    ├── reward_curves_overlay.png  # 叠加对比
    └── q_overestimation.png       # Q值过估计分析

v11.15 — 2026-07-31
"""

import argparse
import copy
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

import numpy as np
import matplotlib
matplotlib.use("Agg")  # 无头模式
import matplotlib.pyplot as plt

# 确定项目根目录
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent.parent.resolve()  # bottlesumo_pi/
REPO_ROOT = PROJECT_ROOT.parent.resolve()  # conversation root (where bottlesumo_pi/ lives)
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "simulation"))  # for lightweight_env

try:
    from bottlesumo_pi.common import Config, DQNAgent
    from lightweight_env import LightweightBottleSumoEnv
except ImportError as e:
    print(f"[ERROR] Import failed: {e}")
    print(f"PROJECT_ROOT={PROJECT_ROOT}")
    sys.exit(1)


# ══════════════════════════════════════════════════════════
# 数据结构
# ══════════════════════════════════════════════════════════

@dataclass
class RunResult:
    """单次训练运行结果"""
    run_id: int
    algorithm: str
    seed: int
    episode_rewards: List[float] = field(default_factory=list)
    q_values: List[float] = field(default_factory=list)
    steps_to_convergence: Optional[int] = None
    final_reward: float = 0.0
    max_reward: float = 0.0
    reward_std: float = 0.0
    training_time: float = 0.0


@dataclass
class ComparisonResult:
    """对比结果"""
    dqn_results: List[RunResult]
    ddqn_results: List[RunResult]
    config_snapshot: Dict[str, Any]
    timestamp: str


# ══════════════════════════════════════════════════════════
# 核心实验
# ══════════════════════════════════════════════════════════

def _build_config(base: Config, use_double: bool, seed: int) -> Config:
    """构建指定算法的 Config（dataclass 浅拷贝 + 覆盖字段）。"""
    cfg = copy.deepcopy(base)
    cfg.use_double_dqn = use_double
    cfg.n_episodes = base.n_episodes  # 保持
    return cfg


def run_single_experiment(
    algorithm: str,
    seed: int,
    n_episodes: int,
    base_config: Config,
    verbose: bool = False,
) -> RunResult:
    """运行单次 DQN 或 DDQN 训练。"""
    np.random.seed(seed)

    cfg = _build_config(base_config, algorithm == "DDQN", seed)

    # 环境
    env = LightweightBottleSumoEnv(
        opponent_profile=cfg.opponent_profile,
        render_mode="none",
        seed=seed,
    )

    # Agent
    agent = DQNAgent(cfg)

    result = RunResult(run_id=seed, algorithm=algorithm, seed=seed)
    start_time = time.time()
    reward_window: List[float] = []
    convergence_threshold = 1.5  # 可根据任务调整

    for episode in range(n_episodes):
        obs, _ = env.reset()
        done = False
        ep_reward = 0.0
        ep_q_values: List[float] = []

        while not done:
            action = agent.select_action(obs, training=True)
            next_obs, reward, terminated, truncated, _ = env.step(action)
            reward = float(np.clip(reward, -100.0, 100.0))
            done = terminated or truncated

            agent.replay_buffer.push(obs, action, reward, next_obs, float(done))
            loss = agent.update()

            ep_reward += reward
            # 记录 Q 值: 取当前状态下最大 Q 值的均值作为近似
            with __import__("torch").no_grad():
                state_t = __import__("torch").FloatTensor(obs).unsqueeze(0).to(agent.device)
                q_val = agent.q_net(state_t).max(dim=1).values.item()
                ep_q_values.append(q_val)

            obs = next_obs

        result.episode_rewards.append(ep_reward)
        result.q_values.append(np.mean(ep_q_values) if ep_q_values else 0.0)

        reward_window.append(ep_reward)
        if len(reward_window) > 100:
            reward_window.pop(0)

        # 收敛检测
        if (result.steps_to_convergence is None and
            len(reward_window) >= 100 and
            np.mean(reward_window) >= convergence_threshold):
            result.steps_to_convergence = episode
            if verbose:
                print(f"  [CONVERGED] episode {episode}")

        if verbose and (episode + 1) % max(1, n_episodes // 5) == 0:
            avg = np.mean(reward_window) if reward_window else 0
            print(f"  Ep {episode+1}/{n_episodes}  avg_rew={avg:.2f}  eps={agent.epsilon:.3f}")

    result.training_time = time.time() - start_time
    result.final_reward = float(result.episode_rewards[-1]) if result.episode_rewards else 0.0
    result.max_reward = float(max(result.episode_rewards)) if result.episode_rewards else 0.0
    tail = result.episode_rewards[-100:] if len(result.episode_rewards) >= 100 else result.episode_rewards
    result.reward_std = float(np.std(tail))

    env.close()
    return result


def run_ablation(
    base_config: Config,
    seeds: List[int],
    n_episodes: int,
    output_dir: Path,
    verbose: bool = False,
) -> ComparisonResult:
    """执行完整消融实验。"""
    dqn_results: List[RunResult] = []
    ddqn_results: List[RunResult] = []

    print(f"\n{'=' * 60}")
    print(f"  DQN vs DDQN Ablation Experiment")
    print(f"  Seeds: {seeds}  |  Episodes/seed: {n_episodes}")
    print(f"  Output: {output_dir}")
    print(f"{'=' * 60}")

    for idx, seed in enumerate(seeds):
        print(f"\n[Seed {seed}] ({idx+1}/{len(seeds)})")

        print(f"  DQN  (Double=False) ...")
        r_dqn = run_single_experiment("DQN", seed, n_episodes, base_config, verbose)
        dqn_results.append(r_dqn)
        print(f"    final={r_dqn.final_reward:.2f}  max={r_dqn.max_reward:.2f}  "
              f"t={r_dqn.training_time:.1f}s")

        print(f"  DDQN (Double=True)  ...")
        r_ddqn = run_single_experiment("DDQN", seed + 10000, n_episodes, base_config, verbose)
        ddqn_results.append(r_ddqn)
        print(f"    final={r_ddqn.final_reward:.2f}  max={r_ddqn.max_reward:.2f}  "
              f"t={r_ddqn.training_time:.1f}s")

    comparison = ComparisonResult(
        dqn_results=dqn_results,
        ddqn_results=ddqn_results,
        config_snapshot={
            "seeds": seeds,
            "n_episodes": n_episodes,
            "opponent": base_config.opponent_profile,
            "hidden_dim": base_config.hidden_dim,
            "lr": base_config.learning_rate,
            "gamma": base_config.gamma,
            "batch_size": base_config.batch_size,
        },
        timestamp=datetime.now().isoformat(),
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    _save_json(comparison, output_dir)
    _generate_report(comparison, output_dir)
    _generate_plots(comparison, output_dir)

    return comparison


# ══════════════════════════════════════════════════════════
# 输出
# ══════════════════════════════════════════════════════════

def _save_json(comparison: ComparisonResult, out: Path):
    data = {
        "timestamp": comparison.timestamp,
        "config": comparison.config_snapshot,
        "dqn": [_run_to_dict(r) for r in comparison.dqn_results],
        "ddqn": [_run_to_dict(r) for r in comparison.ddqn_results],
    }
    with open(out / "raw_results.json", "w") as f:
        json.dump(data, f, indent=2)


def _run_to_dict(r: RunResult) -> dict:
    return {
        "run_id": r.run_id, "algorithm": r.algorithm, "seed": r.seed,
        "final_reward": r.final_reward, "max_reward": r.max_reward,
        "reward_std": r.reward_std, "steps_to_convergence": r.steps_to_convergence,
        "training_time": r.training_time,
        "episode_rewards": r.episode_rewards,
        "q_values": r.q_values,
    }


def _generate_report(comparison: ComparisonResult, out: Path):
    """生成 Markdown 对比报告。"""
    dqn = comparison.dqn_results
    ddqn = comparison.ddqn_results

    def _arr(vals):
        return np.array(vals)

    dqn_final = np.mean([r.final_reward for r in dqn])
    ddqn_final = np.mean([r.final_reward for r in ddqn])
    dqn_max = np.mean([r.max_reward for r in dqn])
    ddqn_max = np.mean([r.max_reward for r in ddqn])
    dqn_std = np.mean([r.reward_std for r in dqn])
    ddqn_std = np.mean([r.reward_std for r in ddqn])
    dqn_time = np.mean([r.training_time for r in dqn])
    ddqn_time = np.mean([r.training_time for r in ddqn])

    dqn_conv = [r.steps_to_convergence for r in dqn if r.steps_to_convergence is not None]
    ddqn_conv = [r.steps_to_convergence for r in ddqn if r.steps_to_convergence is not None]
    dqn_conv_str = f"{np.mean(dqn_conv):.0f}" if dqn_conv else "N/A"
    ddqn_conv_str = f"{np.mean(ddqn_conv):.0f}" if ddqn_conv else "N/A"

    # Q 过估计
    dqn_q_over = []
    ddqn_q_over = []
    for rd, rdd in zip(dqn, ddqn):
        if rd.q_values and rd.episode_rewards:
            tail_q = np.mean(rd.q_values[-100:]) if len(rd.q_values) >= 100 else np.mean(rd.q_values)
            tail_r = np.mean(rd.episode_rewards[-100:]) if len(rd.episode_rewards) >= 100 else np.mean(rd.episode_rewards)
            dqn_q_over.append(tail_q - tail_r)
        if rdd.q_values and rdd.episode_rewards:
            tail_q = np.mean(rdd.q_values[-100:]) if len(rdd.q_values) >= 100 else np.mean(rdd.q_values)
            tail_r = np.mean(rdd.episode_rewards[-100:]) if len(rdd.episode_rewards) >= 100 else np.mean(rdd.episode_rewards)
            ddqn_q_over.append(tail_q - tail_r)

    dqn_over_mean = np.mean(dqn_q_over) if dqn_q_over else 0
    ddqn_over_mean = np.mean(ddqn_q_over) if ddqn_q_over else 0

    # 结论
    winner = "DDQN" if ddqn_final > dqn_final else ("DQN" if dqn_final > ddqn_final else "TIE")
    delta = abs(ddqn_final - dqn_final)

    report = f"""# DQN vs DDQN 消融实验报告

**生成时间**: {comparison.timestamp}
**种子数**: {len(dqn)}  |  **每种子回合数**: {comparison.config_snapshot.get('n_episodes', 'N/A')}
**对手**: {comparison.config_snapshot.get('opponent', 'N/A')}

---

## 汇总对比

| 指标 | DQN | DDQN | Δ |
|------|-----|------|-----|
| 最终平均奖励 | {dqn_final:.3f} | {ddqn_final:.3f} | {ddqn_final - dqn_final:+.3f} |
| 最大平均奖励 | {dqn_max:.3f} | {ddqn_max:.3f} | {ddqn_max - dqn_max:+.3f} |
| 奖励波动 (std) | {dqn_std:.3f} | {ddqn_std:.3f} | {ddqn_std - dqn_std:+.3f} |
| 收敛回合数 | {dqn_conv_str} | {ddqn_conv_str} | — |
| Q值过估计偏差 | {dqn_over_mean:+.3f} | {ddqn_over_mean:+.3f} | {ddqn_over_mean - dqn_over_mean:+.3f} |
| 训练时间 (秒) | {dqn_time:.1f} | {ddqn_time:.1f} | {ddqn_time - dqn_time:+.1f} |

---

## 各种子详情

| Seed | DQN Final | DQN Max | DDQN Final | DDQN Max |
|------|-----------|---------|------------|----------|
"""
    for rd, rdd in zip(dqn, ddqn):
        report += f"| {rd.seed} | {rd.final_reward:.2f} | {rd.max_reward:.2f} | {rdd.final_reward:.2f} | {rdd.max_reward:.2f} |\n"

    report += f"""
---

## 结论

**{'✅ DDQN 胜出' if winner == 'DDQN' else '⚠️ DQN 胜出' if winner == 'DQN' else '⚖️ 平局'}** (Δ = {delta:.3f})

"""

    if ddqn_final > dqn_final:
        report += f"Double DQN 在 {len(dqn)} 次独立运行中平均奖励高出 {delta:.3f}，验证了双网络架构在 BottleSumo 环境中的优势。\n"
    elif dqn_final > ddqn_final:
        report += f"标准 DQN 在本环境中表现更优 (Δ = {delta:.3f})。可能原因：环境简单、过估计不严重、或 DDQN 的保守性在此任务中是劣势。\n"
    else:
        report += "两种算法在统计误差范围内表现相当。DDQN 的额外目标网络在此任务中未带来显著提升。\n"

    if abs(ddqn_over_mean) < abs(dqn_over_mean):
        report += f"\n✅ **DDQN 有效缓解了 Q 值过估计**：|偏差| 从 {abs(dqn_over_mean):.3f} 降至 {abs(ddqn_over_mean):.3f}。\n"

    if ddqn_std < dqn_std:
        report += f"\n✅ **DDQN 训练更稳定**：奖励标准差从 {dqn_std:.3f} 降至 {ddqn_std:.3f}。\n"

    report += f"""
---

## 输出文件

| 文件 | 说明 |
|------|------|
| `raw_results.json` | 完整原始训练数据 |
| `reward_curves.png` | DQN / DDQN 分图 |
| `reward_curves_overlay.png` | 叠加对比图 |
| `q_overestimation.png` | Q值 vs 实际回报分析 |
| `comparison_report.md` | 本报告 |
"""

    with open(out / "comparison_report.md", "w", encoding="utf-8") as f:
        f.write(report)


def _generate_plots(comparison: ComparisonResult, out: Path):
    """生成对比图表。"""
    dqn = comparison.dqn_results
    ddqn = comparison.ddqn_results

    # 对齐长度（取最短）
    min_len = min(
        min(len(r.episode_rewards) for r in dqn),
        min(len(r.episode_rewards) for r in ddqn),
    )

    def _align(arr2d, L):
        return np.array([a[:L] for a in arr2d])

    dqn_rew = _align([r.episode_rewards for r in dqn], min_len)
    ddqn_rew = _align([r.episode_rewards for r in ddqn], min_len)

    dqn_mean = np.mean(dqn_rew, axis=0)
    dqn_std = np.std(dqn_rew, axis=0)
    ddqn_mean = np.mean(ddqn_rew, axis=0)
    ddqn_std = np.std(ddqn_rew, axis=0)

    # --- 分图 ---
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    for r in dqn:
        axes[0].plot(r.episode_rewards[:min_len], alpha=0.2, color="blue", linewidth=0.5)
    axes[0].plot(dqn_mean, color="blue", linewidth=2, label="DQN Mean")
    axes[0].fill_between(range(min_len), dqn_mean - dqn_std, dqn_mean + dqn_std,
                         alpha=0.15, color="blue")
    axes[0].set_title("DQN")
    axes[0].set_xlabel("Episode"); axes[0].set_ylabel("Reward")
    axes[0].legend(); axes[0].grid(alpha=0.3)

    for r in ddqn:
        axes[1].plot(r.episode_rewards[:min_len], alpha=0.2, color="green", linewidth=0.5)
    axes[1].plot(ddqn_mean, color="green", linewidth=2, label="DDQN Mean")
    axes[1].fill_between(range(min_len), ddqn_mean - ddqn_std, ddqn_mean + ddqn_std,
                         alpha=0.15, color="green")
    axes[1].set_title("DDQN (Double)")
    axes[1].set_xlabel("Episode"); axes[1].set_ylabel("Reward")
    axes[1].legend(); axes[1].grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(out / "reward_curves.png", dpi=150, bbox_inches="tight")
    plt.close()

    # --- 叠加图 ---
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(dqn_mean, color="blue", linewidth=2, label="DQN")
    ax.fill_between(range(min_len), dqn_mean - dqn_std, dqn_mean + dqn_std,
                    alpha=0.12, color="blue")
    ax.plot(ddqn_mean, color="green", linewidth=2, label="DDQN (Double)")
    ax.fill_between(range(min_len), ddqn_mean - ddqn_std, ddqn_mean + ddqn_std,
                    alpha=0.12, color="green")
    ax.set_title("DQN vs DDQN — Reward Curve Comparison")
    ax.set_xlabel("Episode"); ax.set_ylabel("Reward")
    ax.legend(); ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(out / "reward_curves_overlay.png", dpi=150, bbox_inches="tight")
    plt.close()

    # --- Q 过估计 ---
    q_len = min(
        min(len(r.q_values) for r in dqn),
        min(len(r.q_values) for r in ddqn),
    )
    dqn_q = _align([r.q_values for r in dqn], q_len)
    ddqn_q = _align([r.q_values for r in ddqn], q_len)
    dqn_r = _align([r.episode_rewards for r in dqn], q_len)
    ddqn_r = _align([r.episode_rewards for r in ddqn], q_len)

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(np.mean(dqn_q, axis=0), color="blue", linestyle="--", label="DQN Q-value")
    ax.plot(np.mean(dqn_r, axis=0), color="blue", linestyle="-", label="DQN Actual Return")
    ax.plot(np.mean(ddqn_q, axis=0), color="green", linestyle="--", label="DDQN Q-value")
    ax.plot(np.mean(ddqn_r, axis=0), color="green", linestyle="-", label="DDQN Actual Return")
    ax.set_title("Q-value vs Actual Return — Overestimation Analysis")
    ax.set_xlabel("Episode"); ax.set_ylabel("Value")
    ax.legend(); ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(out / "q_overestimation.png", dpi=150, bbox_inches="tight")
    plt.close()


# ══════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="DQN vs DDQN Ablation Experiment")
    parser.add_argument("--runs", "-r", type=int, default=3,
                        help="Runs per algorithm (default 3)")
    parser.add_argument("--episodes", "-e", type=int, default=500,
                        help="Episodes per run (default 500)")
    parser.add_argument("--seeds", "-s", type=int, nargs="+",
                        help="Custom seed list (overrides --runs)")
    parser.add_argument("--output", "-o", type=str, default="reports/ablation",
                        help="Output directory (default reports/ablation)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose output")
    parser.add_argument("--opponent", type=str, default="aggressive",
                        choices=["aggressive", "moderate", "passive", "stationary"],
                        help="Opponent profile (default aggressive)")
    parser.add_argument("--lr", type=float, default=3e-4,
                        help="Learning rate (default 3e-4)")

    args = parser.parse_args()

    seeds = args.seeds or [42 + i * 7 for i in range(args.runs)]
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    output_dir = Path(args.output) / f"dqn_vs_ddqn_{timestamp}"

    cfg = Config(
        opponent_profile=args.opponent,
        n_episodes=args.episodes,
        learning_rate=args.lr,
    )

    run_ablation(cfg, seeds, args.episodes, output_dir, args.verbose)

    print(f"\n{'=' * 60}")
    print(f"  Experiment complete!")
    print(f"  Report: {output_dir / 'comparison_report.md'}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
