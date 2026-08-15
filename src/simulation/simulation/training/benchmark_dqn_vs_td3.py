"""
benchmark_dqn_vs_td3.py — DQN (Discrete 21-actions) vs TD3 (Continuous 2-actions)

1-seed, 100-episode quick benchmark to evaluate:
  - Continuous control smoothness (TD3) vs discrete jitter (DQN)
  - Win rate, avg reward, push efficiency
  - Action trajectory analysis

Both agents: untrained (fresh init), exploration enabled.
Purpose: architecture validation before full training.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Tuple

import numpy as np

# Path setup
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.resolve()))  # conversation root
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))  # simulation/

from bottlesumo_pi.simulation.continuous_env import ContinuousBottleSumoEnv
from bottlesumo_pi.simulation.lightweight_env import LightweightBottleSumoEnv
from bottlesumo_pi.common.continuous_agents import TD3Agent, TD3Config
from bottlesumo_pi.common.agent import DQNAgent
from bottlesumo_pi.common.config import Config


def run_dqn_benchmark(env, dqn_agent, episodes: int = 100) -> dict:
    """Run DQN benchmark (discrete 21-action space)."""
    rewards = []
    wins = 0
    total_steps = 0
    actions_used = np.zeros(21, dtype=int)

    for ep in range(episodes):
        obs, _ = env.reset()
        ep_reward = 0.0
        done = False
        truncated = False

        while not (done or truncated):
            action_idx = dqn_agent.select_action(obs, training=True)
            if isinstance(action_idx, np.ndarray):
                action_idx = int(action_idx.item())
            else:
                action_idx = int(action_idx)
            actions_used[action_idx] += 1

            next_obs, reward, done, truncated, _ = env.step(action_idx)
            obs = next_obs
            ep_reward += reward
            total_steps += 1

        rewards.append(ep_reward)
        if ep_reward > 0:
            wins += 1

    return {
        "agent": "DQN (Discrete 21)",
        "episodes": episodes,
        "mean_reward": float(np.mean(rewards)),
        "std_reward": float(np.std(rewards)),
        "win_rate": wins / episodes,
        "total_steps": total_steps,
        "avg_steps_per_ep": total_steps / episodes,
        "reward_history": [float(r) for r in rewards],
        "actions_used": actions_used.tolist(),
    }


def run_td3_benchmark(env, td3_agent, episodes: int = 100) -> dict:
    """Run TD3 benchmark (continuous 2-action space)."""
    rewards = []
    wins = 0
    total_steps = 0
    all_actions = []

    linear_low, linear_high = env.ACTION_LINEAR_LOW, env.ACTION_LINEAR_HIGH
    angular_low, angular_high = env.ACTION_ANGULAR_LOW, env.ACTION_ANGULAR_HIGH

    def scale_action(raw: np.ndarray) -> np.ndarray:
        scaled = np.zeros(2, dtype=np.float32)
        scaled[0] = (raw[0] + 1.0) / 2.0 * (linear_high - linear_low) + linear_low
        scaled[1] = (raw[1] + 1.0) / 2.0 * (angular_high - angular_low) + angular_low
        return scaled

    for ep in range(episodes):
        obs, _ = env.reset()
        ep_reward = 0.0
        done = False
        truncated = False

        while not (done or truncated):
            raw_action = td3_agent.select_action(obs, explore=True)
            scaled = scale_action(raw_action)
            all_actions.append(scaled.tolist())

            next_obs, reward, done, truncated, _ = env.step(scaled)
            obs = next_obs
            ep_reward += reward
            total_steps += 1

        rewards.append(ep_reward)
        if ep_reward > 0:
            wins += 1

    actions_arr = np.array(all_actions)
    return {
        "agent": "TD3 (Continuous 2)",
        "episodes": episodes,
        "mean_reward": float(np.mean(rewards)),
        "std_reward": float(np.std(rewards)),
        "win_rate": wins / episodes,
        "total_steps": total_steps,
        "avg_steps_per_ep": total_steps / episodes,
        "reward_history": [float(r) for r in rewards],
        "action_stats": {
            "linear_mean": float(actions_arr[:, 0].mean()),
            "linear_std": float(actions_arr[:, 0].std()),
            "angular_mean": float(actions_arr[:, 1].mean()),
            "angular_std": float(actions_arr[:, 1].std()),
        },
    }


def generate_report(dqn: dict, td3: dict, out: Path):
    """Generate Markdown comparison report."""
    report = f"""# DQN vs TD3 架构基准测试

> 日期: {datetime.now().strftime('%Y-%m-%d %H:%M')}
> 回合: {dqn['episodes']} episodes (未训练，纯架构对比)

## 综合对比

| 指标 | DQN (Discrete 21) | TD3 (Continuous 2) | 优势 |
|------|:---:|:---:|:---:|
| 平均奖励 | {dqn['mean_reward']:.1f} | {td3['mean_reward']:.1f} | {'TD3' if td3['mean_reward'] > dqn['mean_reward'] else 'DQN'} |
| 奖励波动 | {dqn['std_reward']:.1f} | {td3['std_reward']:.1f} | {'TD3' if td3['std_reward'] < dqn['std_reward'] else 'DQN'} |
| 胜率 | {dqn['win_rate']:.1%} | {td3['win_rate']:.1%} | {'TD3' if td3['win_rate'] > dqn['win_rate'] else 'DQN'} |
| 平均步数 | {dqn['avg_steps_per_ep']:.1f} | {td3['avg_steps_per_ep']:.1f} | {'TD3' if td3['avg_steps_per_ep'] < dqn['avg_steps_per_ep'] else 'DQN'} |

## 动作空间效率

| 指标 | DQN | TD3 |
|------|:---:|:---:|
| 动作维度 | 21 (离散) | 2 (连续) |
| 动作利用率 | {sum(1 for a in dqn.get('actions_used', []) if a > 0)}/21 | N/A (连续) |
| 线性速度 (μ±σ) | N/A | {td3['action_stats']['linear_mean']:.3f} ± {td3['action_stats']['linear_std']:.3f} |
| 角速度 (μ±σ) | N/A | {td3['action_stats']['angular_mean']:.3f} ± {td3['action_stats']['angular_std']:.3f} |

## 结论

- DQN 离散动作: {dqn['mean_reward']:.1f} ± {dqn['std_reward']:.1f}, 胜率 {dqn['win_rate']:.1%}
- TD3 连续动作: {td3['mean_reward']:.1f} ± {td3['std_reward']:.1f}, 胜率 {td3['win_rate']:.1%}

**架构推荐**: 待完整训练后确定。本测试仅验证两种 agent 可以无错误运行。
"""
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n[OK] Report saved: {out}")


if __name__ == "__main__":
    print("=" * 60)
    print(" DQN vs TD3 Architecture Benchmark")
    print("=" * 60)

    EPISODES = 100
    SEED = 42

    # ── DQN Setup (discrete env) ──
    print("\n[1/2] Running DQN (Discrete 21-actions)...")
    dqn_env = LightweightBottleSumoEnv(opponent_profile="aggressive", seed=SEED)
    dqn_cfg = Config()
    dqn_cfg.state_dim = 7
    dqn_cfg.action_dim = 21
    dqn_cfg.device = "cpu"
    dqn_cfg.use_double_dqn = True
    dqn_agent = DQNAgent(dqn_cfg)

    dqn_results = run_dqn_benchmark(dqn_env, dqn_agent, episodes=EPISODES)
    print(f"  DQN: reward={dqn_results['mean_reward']:.1f}±{dqn_results['std_reward']:.1f}  "
          f"win_rate={dqn_results['win_rate']:.1%}")
    dqn_env.close()

    # ── TD3 Setup (continuous env) ──
    print("\n[2/2] Running TD3 (Continuous 2-actions)...")
    td3_env = ContinuousBottleSumoEnv(opponent_profile="aggressive", seed=SEED)
    td3_cfg = TD3Config(
        state_dim=7, action_dim=2, max_action=1.0,
        batch_size=128, buffer_capacity=20000,
        exploration_noise=0.2,
        device="cpu",
    )
    td3_agent = TD3Agent(td3_cfg)

    td3_results = run_td3_benchmark(td3_env, td3_agent, episodes=EPISODES)
    print(f"  TD3: reward={td3_results['mean_reward']:.1f}±{td3_results['std_reward']:.1f}  "
          f"win_rate={td3_results['win_rate']:.1%}")
    td3_env.close()

    # ── Report ──
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_dir = Path("reports/continuous_rl") / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save raw JSON
    with open(out_dir / "benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump({"dqn": dqn_results, "td3": td3_results}, f, indent=2)
    print(f"[OK] JSON saved: {out_dir / 'benchmark_results.json'}")

    # Generate report
    generate_report(dqn_results, td3_results, out_dir / "comparison_report.md")

    print("\n" + "=" * 60)
    print(" Benchmark complete!")
    print(f" Output: {out_dir}")
    print("=" * 60)
