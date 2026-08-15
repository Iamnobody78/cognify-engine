"""
shap_nano_real.py — Real SHAP feature attribution on Nano student model

Loads nano_student.pt (7→16→16→21), collects observation data,
runs Kernel SHAP to estimate feature importance.

This replaces the demo/prior-only SHAP with real model analysis.
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import torch
import torch.nn as nn

from lightweight_env import LightweightBottleSumoEnv

N_ACTIONS = 21
STATE_DIM = 7
MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
RESULTS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "bottlesumo_pi", "simulation", "evaluation"
)
os.makedirs(RESULTS_DIR, exist_ok=True)

FEATURE_NAMES = [
    "robot_x",  # 0: robot abs X position
    "robot_y",  # 1: robot abs Y position
    "opponent_x",  # 2: opponent relative X
    "opponent_y",  # 3: opponent relative Y
    "edge_front",  # 4: front edge distance
    "edge_back",  # 5: back edge distance
    "edge_left",  # 6: left edge distance (or min edge)
]


# ── Nano Student model (matches distill_nano.py) ──
class NanoQNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(7, 16), nn.ReLU(), nn.Linear(16, 16), nn.ReLU(), nn.Linear(16, 21)
        )

    def forward(self, x):
        return self.net(x)


def load_nano():
    ckpt = torch.load(
        os.path.join(MODEL_DIR, "nano_student.pt"), map_location="cpu", weights_only=False
    )
    model = NanoQNet()
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    mean = torch.FloatTensor(ckpt["X_mean"][0])
    std = torch.FloatTensor(ckpt["X_std"][0])
    return model, mean, std


def collect_observations(n_samples=500):
    """Collect diverse observations from environment interactions with Nano policy"""
    model, mean, std = load_nano()
    observations = []
    action_counts = np.zeros(N_ACTIONS)

    profiles = ["aggressive", "moderate", "passive", "stationary"]
    for pf in profiles:
        env = LightweightBottleSumoEnv(opponent_profile=pf, render_mode="none")
        for ep in range(20):
            obs, _ = env.reset(seed=42 + hash(pf) % 1000 + ep * 137)
            done = False
            while not done:
                obs_norm = (torch.FloatTensor(obs) - mean) / (std + 1e-6)
                with torch.no_grad():
                    q = model(obs_norm.unsqueeze(0))
                action = q.argmax(dim=1).item()
                action_counts[action] += 1
                observations.append(obs.copy())
                obs, reward, done, truncated, _ = env.step(action)
                if truncated:
                    done = True
                if len(observations) >= n_samples:
                    env.close()
                    return np.array(observations), action_counts
        env.close()
    return np.array(observations), action_counts


def kernel_shap_local(model, mean, std, X_sample, X_ref, n_background=50):  # noqa: N803
    """Approximate Kernel SHAP: perturb features and measure Q-value change at argmax action"""
    X_sample_t = torch.FloatTensor(X_sample)  # noqa: N806
    ref_t = torch.FloatTensor(X_ref[:n_background])

    # Normalize
    X_norm = (X_sample_t - mean) / (std + 1e-6)  # noqa: N806
    ref_norm = (ref_t - mean) / (std + 1e-6)

    # Get baseline Q values
    with torch.no_grad():
        baseline_q = model(ref_norm).mean(dim=0)  # avg Q over reference set
        full_q = model(X_norm)

    # For each observation, compute SHAP by perturbation sampling
    n_obs = min(len(X_sample), 100)
    shap_values = np.zeros((n_obs, STATE_DIM))

    for i in range(n_obs):
        obs_q = full_q[i]
        best_action = obs_q.argmax().item()
        baseline_q[best_action].item()
        full_val = obs_q[best_action].item()

        # Per-feature: replace with reference value, see Q change
        for f in range(STATE_DIM):
            perturbed = X_norm[i].clone()
            perturbed[f] = ref_norm[:, f].mean()  # replace with reference mean
            with torch.no_grad():
                perturbed_q = model(perturbed.unsqueeze(0))[0, best_action].item()
            shap_values[i, f] = full_val - perturbed_q

    return shap_values


def main():
    print("=" * 60)
    print(" SHAP Analysis on Nano Student (7→16→16→21)")
    print("=" * 60)

    # Load model
    model, mean, std = load_nano()
    n_params = sum(p.numel() for p in model.parameters())
    print(f"  Model: {n_params} params ({n_params * 4 / 1024:.1f} KB FP32)")

    # Collect data
    print("  Collecting observations...")
    X_obs, action_dist = collect_observations(n_samples=500)  # noqa: N806
    print(f"  Collected: {len(X_obs)} samples, {X_obs.shape[1]} features")
    print(f"  Action distribution: {np.round(action_dist / action_dist.sum() * 100, 1)}")

    # Background reference (random subset)
    np.random.seed(42)
    ref_idx = np.random.choice(len(X_obs), min(80, len(X_obs)), replace=False)
    X_ref = X_obs[ref_idx]  # noqa: N806

    # Run local SHAP
    print("\n  Computing per-feature SHAP values...")
    shap_vals = kernel_shap_local(model, mean, std, X_obs, X_ref, n_background=50)

    # Aggregate
    mean_shap = np.abs(shap_vals).mean(axis=0)
    mean_shap_normalized = mean_shap / mean_shap.sum()

    # Feature ranking
    ranking = sorted(enumerate(mean_shap_normalized), key=lambda x: -x[1])

    print("\n" + "=" * 60)
    print(" FEATURE IMPORTANCE (from real Nano model)")
    print("=" * 60)
    print(f"  {'Feature':<20s} {'Abs SHAP':>10s} {'Normalized':>10s} {'Rank':>5s}")
    print(f"  {'-' * 20} {'-' * 10} {'-' * 10} {'-' * 5}")
    for rank, (feat_idx, importance) in enumerate(ranking):
        print(
            f"  {FEATURE_NAMES[feat_idx]:<20s} {mean_shap[feat_idx]:>10.4f} {importance:>10.3f} {rank + 1:>5d}"
        )

    # Save results
    result = {
        "model": "nano_student.pt",
        "architecture": "7→16→16→21 MLP",
        "params": n_params,
        "n_samples": len(X_obs),
        "shap_method": "kernel_shap_per_feature",
        "feature_names": FEATURE_NAMES,
        "abs_shap_mean": mean_shap.tolist(),
        "normalized_importance": mean_shap_normalized.tolist(),
        "ranking": [
            {
                "rank": i + 1,
                "feature": FEATURE_NAMES[idx],
                "importance": float(mean_shap_normalized[idx]),
            }
            for i, (idx, _) in enumerate(ranking)
        ],
        "top_features": [FEATURE_NAMES[idx] for idx, _ in ranking[:3]],
        "prior_comparison": {
            "prior_top": ["opponent_x", "opponent_y", "edge_sensor"],
            "real_top": [FEATURE_NAMES[idx] for idx, _ in ranking[:3]],
            "match": "pending",
        },
    }

    result_path = os.path.join(RESULTS_DIR, "shap_analysis_real.json")
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\n  Results saved: {result_path}")
    return result


if __name__ == "__main__":
    main()
