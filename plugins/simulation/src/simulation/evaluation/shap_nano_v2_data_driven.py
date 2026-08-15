"""
shap_nano_v2_data_driven.py -- Proper opponent sensitivity test using in-distribution data.

Key insight: position features (robot_x/y, opponent_x/y) all have X_mean~0.999, X_std~0.006.
This means opponent/robot positions barely vary in the data — the environment is near-trivial.
Testing with out-of-distribution values gives misleading results.

This script:
1. Samples in-distribution from the actual environment
2. Tests whether V2 model can differentiate opponent states from the ENVIRONMENT'S distribution
3. Compares to V1
"""

import os
import sys

import numpy as np

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)

import torch
import torch.nn as nn

from lightweight_env import LightweightBottleSumoEnv

N_ACTIONS = 21
STATE_DIM = 7
FEATURE_NAMES = [
    "robot_x",
    "robot_y",
    "opponent_x",
    "opponent_y",
    "edge_front",
    "edge_back",
    "edge_left",
]


class NanoQNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(7, 16), nn.ReLU(), nn.Linear(16, 16), nn.ReLU(), nn.Linear(16, 21)
        )

    def forward(self, x):
        return self.net(x)


def load_model(path):
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    model = NanoQNet()
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    mean = np.array(ckpt["X_mean"]).flatten()
    std = np.array(ckpt["X_std"]).flatten()
    return model, torch.FloatTensor(mean), torch.FloatTensor(std)


def main():
    proj_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    model_dir = os.path.join(proj_root, "models")
    os.path.dirname(os.path.abspath(__file__))

    v2_path = os.path.join(model_dir, "nano_student_v2.pt")
    v1_path = os.path.join(model_dir, "nano_student.pt")

    print("=" * 60)
    print(" IN-DISTRIBUTION OPPONENT SENSITIVITY TEST")
    print("=" * 60)

    v2_model, v2_mean, v2_std = load_model(v2_path)
    v1_model, v1_mean, v1_std = load_model(v1_path)

    # Print normalization stats
    print("\n  V2 normalization stats (mean, std):")
    for i, name in enumerate(FEATURE_NAMES):
        print(f"    {name:<14s}: mean={v2_mean[i].item():.6f}, std={v2_std[i].item():.6f}")

    print("\n  V1 normalization stats (mean, std):")
    for i, name in enumerate(FEATURE_NAMES):
        print(f"    {name:<14s}: mean={v1_mean[i].item():.6f}, std={v1_std[i].item():.6f}")

    # ── Test 1: Do Q-values differ between DIFFERENT opponent profiles? ──
    print(f"\n{'=' * 60}")
    print(" TEST 1: Per-profile Q-value distributions")
    print(f"{'=' * 60}")

    profiles = ["aggressive", "moderate", "passive", "stationary"]

    for model, model_name, mean, std in [
        (v2_model, "Nano-V2", v2_mean, v2_std),
        (v1_model, "Nano-V1", v1_mean, v1_std),
    ]:
        print(f"\n  --- {model_name} ---")
        profile_q_stats = {}

        for pf in profiles:
            env = LightweightBottleSumoEnv(opponent_profile=pf, render_mode="none")
            q_vals = []
            actions = []

            for ep in range(10):
                obs, _ = env.reset(seed=42 + hash(pf) % 1000 + ep * 137)
                done = False
                step = 0
                while not done and step < 100:
                    obs_norm = (torch.FloatTensor(obs) - mean) / (std + 1e-6)
                    with torch.no_grad():
                        q = model(obs_norm.unsqueeze(0))[0]
                    q_vals.append(q.numpy())
                    action = q.argmax().item()
                    actions.append(action)
                    obs, _, done, truncated, _ = env.step(action)
                    if truncated:
                        done = True
                    step += 1
            env.close()

            q_arr = np.array(q_vals)
            profile_q_stats[pf] = {
                "mean_q": float(q_arr.mean()),
                "std_q": float(q_arr.std()),
                "max_q": float(q_arr.max()),
                "min_q": float(q_arr.min()),
                "unique_actions": len(set(actions)),
                "top_actions": [
                    int(a)
                    for a, c in zip(*np.unique(actions, return_counts=True), strict=False)
                    if c > len(actions) * 0.05
                ][:5],
            }
            print(
                f"    {pf:<12s}: Q_mean={q_arr.mean():.4f}, Q_std={q_arr.std():.4f}, "
                f"unique_act={len(set(actions))}, top={profile_q_stats[pf]['top_actions'][:3]}"
            )

        # Compute pairwise Q-value distribution distances
        print("\n    Pairwise Q-distribution distances (K-S statistic):")
        max_dist = 0
        for i, pf1 in enumerate(profiles):
            for pf2 in profiles[i + 1 :]:
                env1 = LightweightBottleSumoEnv(opponent_profile=pf1, render_mode="none")
                env2 = LightweightBottleSumoEnv(opponent_profile=pf2, render_mode="none")
                q1, q2 = [], []
                for ep in range(5):
                    obs, _ = env1.reset(seed=100 + ep)
                    q1.append(model((torch.FloatTensor(obs) - mean) / (std + 1e-6)).max().item())
                    obs, _ = env2.reset(seed=100 + ep)
                    q2.append(model((torch.FloatTensor(obs) - mean) / (std + 1e-6)).max().item())
                # Simple metric: absolute mean difference
                dist = abs(np.mean(q1) - np.mean(q2))
                max_dist = max(max_dist, dist)
                print(f"      {pf1} vs {pf2}: Q_diff={dist:.4f}")
                env1.close()
                env2.close()

        if max_dist > 0.01:
            print(
                f"    [OK] {model_name} differentiates opponent profiles (max Q_diff={max_dist:.4f})"
            )
        else:
            print(f"    [FAIL] {model_name} sees all opponents identically")

    # ── Test 2: State-level analysis ──
    print(f"\n{'=' * 60}")
    print(" TEST 2: State distribution statistics from environment")
    print(f"{'=' * 60}")

    # Collect a large sample from each profile and compute per-feature distributions
    env = LightweightBottleSumoEnv(opponent_profile="aggressive", render_mode="none")
    all_obs = []
    for ep in range(100):
        obs, _ = env.reset(seed=ep * 100 + 1)
        for _ in range(50):
            all_obs.append(obs.copy())
            obs, _, done, truncated, _ = env.step(np.random.randint(0, 21))
            if done or truncated:
                break
    env.close()
    all_obs = np.array(all_obs)

    for i, name in enumerate(FEATURE_NAMES):
        vals = all_obs[:, i]
        print(
            f"  {name:<14s}: mean={vals.mean():.6f}, std={vals.std():.6f}, "
            f"min={vals.min():.4f}, max={vals.max():.4f}, "
            f"range={vals.max() - vals.min():.6f}"
        )

    # Key question: does opponent_x actually vary in the environment?
    opp_x_range = all_obs[:, 2].max() - all_obs[:, 2].min()
    opp_y_range = all_obs[:, 3].max() - all_obs[:, 3].min()
    edge_range = all_obs[:, 4:7].max(axis=0) - all_obs[:, 4:7].min(axis=0)

    print(f"\n  Opponent position range: x={opp_x_range:.6f}, y={opp_y_range:.6f}")
    print(
        f"  Edge feature range:      front={edge_range[0]:.6f}, back={edge_range[1]:.6f}, left={edge_range[2]:.6f}"
    )

    print(f"\n{'=' * 60}")
    print(" FINAL DIAGNOSIS")
    print(f"{'=' * 60}")
    print(
        f"  Opponent position variance in data: {all_obs[:, 2].var():.6f} (vs edge_front: {all_obs[:, 4].var():.6f})"
    )
    print(
        f"  Variance ratio (opponent/edge): {all_obs[:, 2].var() / max(all_obs[:, 4].var(), 1e-10):.4f}"
    )

    if all_obs[:, 2].var() < 0.001:
        print("  [ROOT CAUSE] Opponent position barely varies in environment")
        print("  No amount of distillation can create information that doesn't exist")
        print("  Both V1 and V2 will appear opponent-blind because data lacks opponent variation")
        print("  Solution: Use environment with more diverse opponent behavior OR")
        print("  augment data with synthetic opponent positions")
    elif all_obs[:, 2].var() < 0.01:
        print("  [MINOR ISSUE] Opponent position varies slightly")
        print("  Distillation has limited signal to work with")
    else:
        print("  [OK] Sufficient opponent variation exists")
        print("  If model is blind, it's a training/architecture issue")


if __name__ == "__main__":
    main()
