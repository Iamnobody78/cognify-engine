"""
evaluation — unified evaluation function with configurable thresholds.

Replaces 5+ inconsistent evaluate() implementations across train/eval scripts.
"""

import numpy as np
import torch


def evaluate(
    model: torch.nn.Module,
    env,
    n_episodes: int = 30,
    win_threshold: float = 100.0,
    edge_threshold: float = -50.0,
    device: torch.device | None = None,
    verbose: bool = True,
) -> dict:
    """Evaluate a Q-network in the given environment.

    Args:
        model: Trained Q-network (in eval mode).
        env: Gym-like environment with reset() + step().
        n_episodes: Number of evaluation episodes.
        win_threshold: Reward above this counts as a win.
        edge_threshold: Reward below this counts as an edge drop.
        device: torch device (auto-detect if None).
        verbose: Print per-episode summary.

    Returns:
        dict with keys: win_rate_pct, win_count, edge_drops, avg_reward, std_reward, total
    """
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model.eval()
    wins = 0
    edges = 0
    episode_rewards = []
    total_episodes = 0

    for _ep in range(n_episodes):
        obs, _ = env.reset()
        done = False
        ep_reward = 0.0

        while not done:
            with torch.no_grad():
                state_t = torch.FloatTensor(obs).unsqueeze(0).to(device)
                action = model(state_t).argmax(dim=1).item()
            obs, reward, done, truncated, _ = env.step(action)
            ep_reward += reward
            if truncated:
                done = True

        total_episodes += 1

        if ep_reward >= win_threshold:
            wins += 1
        elif ep_reward <= edge_threshold:
            edges += 1

        episode_rewards.append(ep_reward)

    win_rate = wins / total_episodes * 100 if total_episodes > 0 else 0.0
    avg_reward = float(np.mean(episode_rewards))
    std_reward = float(np.std(episode_rewards))

    if verbose:
        print(
            f"  Eval: WR={win_rate:5.1f}% | wins={wins}/{total_episodes} "
            f"| drops={edges} | avgR={avg_reward:7.1f} ± {std_reward:.1f}"
        )

    return {
        "win_rate_pct": win_rate,
        "win_count": wins,
        "edge_drops": edges,
        "avg_reward": avg_reward,
        "std_reward": std_reward,
        "total": total_episodes,
    }
