"""
train.py — Refactored BottleSumo DQN training pipeline.

Uses bottlesumo_pi.common for all shared infrastructure.
Replaces: train_dqn_v10.py, train_v10d_batch.py, train_v10e_extended.py

Usage:
    python train.py                          # default config
    python train.py --config bayesopt        # BayeOpt best config
    python train.py --config nano            # Nano student config
    python train.py --config quick_test      # CI / smoke test
"""

import argparse
import json
import os
import sys
import time

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bottlesumo_pi.common import Config, DQNAgent, evaluate
from lightweight_env import LightweightBottleSumoEnv

# ── Curriculum profiles ──
# Sprint 36 T3 iter-1 (FP-RL-001): speed ladder never sampled retreat/orbit
# dynamics → DQN OOD-blind to gate's defensive/circler (0/2 each).
# Sprint 36 T3 iter-2 (FP-RL-002): single-pass stage ladder caused catastrophic
# forgetting — circler/defensive skills learned at ep 0-187 were overwritten by
# later ladder stages (final model 0/2 again, and random dropped 2/2→0/2 from
# budget dilution). Fixed by ROUND-ROBIN rotation.
# Sprint 37 T2 (PM 裁决): WEIGHTED round-robin — gate behavioral profiles ×2 +
# speed ladder ×1 (13-slot cycle): every gate profile gets 2/13 = 15.4% of
# episodes (满足 ≥15% 验收), no stage forgetting, no budget dilution.
from v9_gate_evaluator import OpponentStrategies

GATE_BEHAVIORS = {
    "defensive": OpponentStrategies.get("defensive"),
    "circler": OpponentStrategies.get("circler"),
    "counter": OpponentStrategies.get("counter"),
    "random": OpponentStrategies.get("random"),
}
CURRICULUM_POOL = [
    "random", "aggressive", "defensive", "circler", "counter",  # gate suite ×2
    "random", "aggressive", "defensive", "circler", "counter",
    "moderate", "passive", "stationary",                        # speed ladder ×1
]


def train_episode(agent: DQNAgent, env, episode: int, cfg: Config):
    """Run one training episode. Returns (total_reward, steps, opponent_oob)."""
    obs, _ = env.reset()
    done = False
    ep_reward = 0.0
    steps = 0

    while not done:
        action = agent.select_action(obs, training=True)
        next_obs, reward, done, truncated, _ = env.step(action)
        reward = np.clip(
            reward, -100.0, 100.0
        )  # numerical stability for BayesOpt high edge_penalty
        agent.replay_buffer.push(obs, action, reward, next_obs, float(done))
        agent.update()
        obs = next_obs
        ep_reward += reward
        steps += 1
        if truncated:
            done = True

    return ep_reward, steps


def train(cfg: Config, curriculum: bool = True, init_weights: str | None = None):
    """Main training loop."""
    print(f"╔{'═' * 60}╗")
    print(f"║  BottleSumo DQN Training {'':>30s}║")
    print(f"║  Config: {cfg.save_name:>48s}  ║")
    print(f"╚{'═' * 60}╝")
    print(
        f"  Double DQN: {cfg.use_double_dqn} | LR: {cfg.learning_rate} | Episodes: {cfg.n_episodes}"
    )
    print(
        f"  Architecture: {cfg.state_dim}→{cfg.hidden_dim}→{cfg.action_dim} ({cfg.n_hidden} hidden layers)"
    )
    print(
        f"  Reward: edge_penalty_weight={cfg.edge_penalty_weight:.2f} push_threshold={cfg.push_threshold:.3f}"
    )
    if init_weights:
        print(f"  Warm-start: {init_weights} (S36 T2 ABDL teacher BC)")
    print()

    agent = DQNAgent(cfg)
    if init_weights:
        if not os.path.isfile(init_weights):
            raise FileNotFoundError(f"init_weights not found: {init_weights}")
        agent.q_net.load_state_dict(
            torch.load(init_weights, map_location="cpu", weights_only=True)
        )
        print(f"  Loaded teacher warm-start weights: {init_weights}")
    eval_env = LightweightBottleSumoEnv(
        opponent_profile=cfg.opponent_profile,
        render_mode="none",
        seed=cfg.n_episodes + 9999,
        edge_penalty_weight=cfg.edge_penalty_weight,
        push_threshold=cfg.push_threshold,
    )
    train_env = LightweightBottleSumoEnv(
        opponent_profile=cfg.opponent_profile,
        render_mode="none",
        seed=42,
        edge_penalty_weight=cfg.edge_penalty_weight,
        push_threshold=cfg.push_threshold,
    )

    history = {"episode": [], "reward": [], "win_rate": [], "epsilon": [], "loss": []}
    best_wr = 0.0
    t_start = time.time()

    for ep in range(cfg.n_episodes):
        # Sprint 37 T2 weighted round-robin curriculum: rotate through the
        # 13-slot pool (gate behavioral profiles ×2 + speed ladder ×1) so every
        # gate profile gets 15.4% of episodes (≥15% 验收) with no stage
        # forgetting (FP-RL-002 fix) and no budget dilution.
        if curriculum:
            profile = CURRICULUM_POOL[ep % len(CURRICULUM_POOL)]
            train_env.close()
            if profile in GATE_BEHAVIORS:
                # Gate behavioral strategy (defensive/circler/counter/random).
                # S38 T2: defensive 物理不对称 0.50 (0.53→0.265) 与门评估一致 —
                # 避免训练满速 defensive / 评估慢速 defensive 的分布漂移。
                train_env = LightweightBottleSumoEnv(
                    opponent_strategy=GATE_BEHAVIORS[profile],
                    # S38 T2: defensive 物理不对称 0.40 (门协议一致) — 训练-评估
                    # 分布对齐 (0.50 时代 S37 门 0/8; 0.40 时代 S38 门 5/8)。
                    opponent_speed_scale=(0.40 if profile == "defensive" else 1.0),
                    render_mode="none",
                    seed=42 + ep,
                    edge_penalty_weight=cfg.edge_penalty_weight,
                    push_threshold=cfg.push_threshold,
                )
            else:
                train_env = LightweightBottleSumoEnv(
                    opponent_profile=profile,
                    render_mode="none",
                    seed=42 + ep,
                    edge_penalty_weight=cfg.edge_penalty_weight,
                    push_threshold=cfg.push_threshold,
                )

        ep_reward, steps = train_episode(agent, train_env, ep, cfg)
        history["episode"].append(ep)
        history["reward"].append(ep_reward)

        # Evaluation
        if (ep + 1) % cfg.eval_freq == 0 or ep == 0 or ep == cfg.n_episodes - 1:
            result = evaluate(
                agent.q_net,
                eval_env,
                n_episodes=cfg.eval_episodes,
                win_threshold=cfg.win_threshold,
                edge_threshold=cfg.edge_threshold,
                verbose=False,
            )
            wr = result["win_rate_pct"]
            history["win_rate"].append(wr)
            history["epsilon"].append(agent.epsilon)

            improved = "↑" if wr > best_wr else " "
            if wr > best_wr:
                best_wr = wr
                agent.save(cfg.save_path + ".best")

            elapsed = time.time() - t_start
            print(
                f"  Ep {ep + 1:4d}/{cfg.n_episodes} | WR={wr:5.1f}% {improved} "
                f"| drops={result['edge_drops']} | R={result['avg_reward']:7.1f} "
                f"| eps={agent.epsilon:.3f} | {elapsed:.0f}s"
            )

    train_env.close()

    # Final evaluation
    print(f"\n{'─' * 60}")
    print(f"  Final evaluation ({cfg.eval_episodes * 3} episodes)...")
    final_result = evaluate(
        agent.q_net,
        eval_env,
        n_episodes=cfg.eval_episodes * 3,
        win_threshold=cfg.win_threshold,
        edge_threshold=cfg.edge_threshold,
    )

    agent.save(cfg.save_path)

    # Save training history (convert numpy types for JSON)
    os.makedirs(cfg.save_dir, exist_ok=True)
    history_path = cfg.save_path.replace(".pt", "_history.json")
    for key in history:
        history[key] = [float(v) if hasattr(v, "item") else v for v in history[key]]
    with open(history_path, "w") as f:
        json.dump(history, f)

    elapsed = time.time() - t_start
    print(f"\n{'═' * 60}")
    print(
        f"  Training complete: {cfg.n_episodes} episodes in {elapsed:.0f}s ({elapsed / 60:.1f}min)"
    )
    print(f"  Final: WR={final_result['win_rate_pct']:.1f}% | Best: WR={best_wr:.1f}%")
    print(f"  Saved: {os.path.abspath(cfg.save_path)}")
    print(f"{'═' * 60}")

    eval_env.close()
    return final_result, best_wr


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        choices=["default", "bayesopt", "bayesopt_dqn", "nano", "quick_test"],
        default="default",
        help="Config preset",
    )
    parser.add_argument("--no-curriculum", action="store_true", help="Disable curriculum")
    parser.add_argument("--save-name", type=str, default=None, help="Override save name")
    parser.add_argument(
        "--init-weights", type=str, default=None,
        help="S36 T2: ABDL teacher BC warm-start weights (.pt)",
    )
    parser.add_argument(
        "--episodes", type=int, default=None,
        help="S36: override n_episodes (e.g. 500 for convergence check)",
    )
    args = parser.parse_args()

    config_map = {
        "default": Config(),
        "bayesopt": Config.bayesopt_best(),
        "bayesopt_dqn": Config.bayesopt_dqn(),
        "nano": Config.nano(),
        "quick_test": Config.quick_test(),
    }
    cfg = config_map[args.config]
    if args.save_name:
        cfg.save_name = args.save_name
    if args.episodes:
        cfg.n_episodes = args.episodes

    train(cfg, curriculum=not args.no_curriculum, init_weights=args.init_weights)


if __name__ == "__main__":
    main()
