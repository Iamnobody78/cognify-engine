"""
eval.py — Unified evaluation script for all BottleSumo models.

Replaces: eval_v10.py, eval_v10c.py, eval_best_model.py
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import torch

from bottlesumo_pi.common import DQN, Config, evaluate
from lightweight_env import LightweightBottleSumoEnv

MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
RESULTS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "bottlesumo_pi", "tests", "results"
)
os.makedirs(RESULTS_DIR, exist_ok=True)

PROFILES = ["aggressive", "moderate", "passive", "stationary"]


def load_model(
    path: str, state_dim: int = 7, action_dim: int = 21, hidden_dim: int = 128, n_hidden: int = 2
) -> DQN:
    """Load a trained DQN model from checkpoint."""
    model = DQN(state_dim, action_dim, hidden_dim, n_hidden)
    state_dict = torch.load(path, map_location="cpu", weights_only=True)
    model.load_state_dict(state_dict)
    model.eval()
    return model


def benchmark(model_path: str, cfg: Config, n_eps: int = 50):
    """Full multi-profile benchmark."""
    print(f"╔{'═' * 60}╗")
    print(f"║  BottleSumo Model Benchmark{'':>32s}║")
    print(f"║  Model: {os.path.basename(model_path):>48s}  ║")
    print(f"╚{'═' * 60}╝\n")

    model = load_model(model_path, cfg.state_dim, cfg.action_dim, cfg.hidden_dim, cfg.n_hidden)

    results = {}
    for profile in PROFILES:
        env = LightweightBottleSumoEnv(
            opponent_profile=profile, render_mode="none", seed=42 + hash(profile) % 1000
        )
        r = evaluate(
            model,
            env,
            n_episodes=n_eps,
            win_threshold=cfg.win_threshold,
            edge_threshold=cfg.edge_threshold,
        )
        results[profile] = r
        env.close()
        print(
            f"  {profile:<15s}: WR={r['win_rate_pct']:5.1f}% | drops={r['edge_drops']}/{r['total']} | avgR={r['avg_reward']:7.1f}"
        )

    # Summary
    overall_wr = np.mean([r["win_rate_pct"] for r in results.values()])
    overall_drops = sum(r["edge_drops"] for r in results.values())
    total_eps = sum(r["total"] for r in results.values())

    print(f"\n{'─' * 60}")
    print(f"  Overall: WR={overall_wr:.1f}% | drops={overall_drops}/{total_eps}")
    print(f"{'═' * 60}")

    # Save
    report = {
        "model": os.path.basename(model_path),
        "n_episodes_per_profile": n_eps,
        "results": {
            k: {
                "win_rate_pct": v["win_rate_pct"],
                "edge_drops": v["edge_drops"],
                "avg_reward": v["avg_reward"],
                "total": v["total"],
            }
            for k, v in results.items()
        },
        "overall_win_rate_pct": float(overall_wr),
        "overall_edge_drops": overall_drops,
    }
    report_path = os.path.join(
        RESULTS_DIR, os.path.basename(model_path).replace(".pt", "_benchmark.json")
    )
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"  Report: {report_path}")

    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model", type=str, default="v10_dqn_best.pt", help="Model file in models/ directory"
    )
    parser.add_argument(
        "--n-episodes", type=int, default=50, help="Evaluation episodes per profile"
    )
    parser.add_argument("--hidden-dim", type=int, default=128)
    parser.add_argument("--n-layers", type=int, default=2)
    args = parser.parse_args()

    model_path = os.path.join(MODEL_DIR, args.model)
    if not os.path.exists(model_path):
        print(f"ERROR: Model not found: {model_path}")
        sys.exit(1)

    cfg = Config(hidden_dim=args.hidden_dim, n_hidden=args.n_layers)
    benchmark(model_path, cfg, n_eps=args.n_episodes)


if __name__ == "__main__":
    import numpy as np

    main()
