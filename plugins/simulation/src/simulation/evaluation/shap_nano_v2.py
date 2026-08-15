"""
shap_nano_v2.py — SHAP feature attribution on Nano V2 student model.

Loads nano_student_v2.pt (opponent-aware distilled, 7→16→16→21),
collects observation data, runs perturbation-based SHAP to estimate
feature importance. Compares with V1 baseline to verify opponent
feature preservation (target: opponent_x/opponent_y > 10% combined).
"""

import json
import os
import sys
import time

import numpy as np

# Add project root for lightweight_env and bottlesumo_pi imports
_PROJ_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
sys.path.insert(0, _PROJ_ROOT)

import torch  # noqa: E402
import torch.nn as nn  # noqa: E402

from lightweight_env import LightweightBottleSumoEnv  # noqa: E402

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
    "edge_left",  # 6: left edge distance
]


# -- Nano Student model (7→16→16→21, matches distill_nano.py and distill_nano_v2.py) --
class NanoQNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(7, 16), nn.ReLU(), nn.Linear(16, 16), nn.ReLU(), nn.Linear(16, 21)
        )

    def forward(self, x):
        return self.net(x)


def load_model(model_path, name="model"):
    """Load nano model checkpoint with normalization stats."""
    ckpt = torch.load(model_path, map_location="cpu", weights_only=False)
    model = NanoQNet()
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    mean = torch.FloatTensor(ckpt["X_mean"][0])
    std = torch.FloatTensor(ckpt["X_std"][0])
    n_params = sum(p.numel() for p in model.parameters())
    print(
        f"  [{name}] {n_params} params, X_mean range: [{mean.min():.4f}, {mean.max():.4f}], X_std range: [{std.min():.4f}, {std.max():.4f}]"
    )
    return model, mean, std


def collect_observations(model, mean, std, n_samples=500):
    """Collect diverse observations using the model's policy across opponent profiles."""
    observations = []
    action_counts = np.zeros(N_ACTIONS)

    profiles = ["aggressive", "moderate", "passive", "stationary"]
    for pf in profiles:
        env = LightweightBottleSumoEnv(opponent_profile=pf, render_mode="none")
        for ep in range(25):
            obs, _ = env.reset(seed=42 + hash(pf) % 1000 + ep * 137)
            done = False
            step_count = 0
            while not done and step_count < 500:
                obs_norm = (torch.FloatTensor(obs) - mean) / (std + 1e-6)
                with torch.no_grad():
                    q = model(obs_norm.unsqueeze(0))
                action = q.argmax(dim=1).item()
                action_counts[action] += 1
                observations.append(obs.copy())
                obs, reward, done, truncated, _ = env.step(action)
                if truncated:
                    done = True
                step_count += 1
                if len(observations) >= n_samples:
                    env.close()
                    return np.array(observations), action_counts
            if len(observations) >= n_samples:
                env.close()
                return np.array(observations), action_counts
        env.close()
    return np.array(observations), action_counts


def perturbation_shap(model, mean, std, X_sample, X_ref, n_background=50, n_obs=100):  # noqa: N803
    """
    Per-feature perturbation SHAP: replace each feature with reference mean,
    measure Q-value change at best action.

    SHAP φ_i ≈ f(x) - f(x_{i→ref})
    """
    X_sample_t = torch.FloatTensor(X_sample)  # noqa: N806
    ref_t = torch.FloatTensor(X_ref[:n_background])

    # Normalize
    X_norm = (X_sample_t - mean) / (std + 1e-6)  # noqa: N806
    ref_norm = (ref_t - mean) / (std + 1e-6)

    # Baseline Q (average over reference set)
    with torch.no_grad():
        baseline_q = model(ref_norm).mean(dim=0)

    n_obs = min(len(X_sample), n_obs)
    shap_values = np.zeros((n_obs, STATE_DIM))

    for i in range(n_obs):
        obs_q_norm = X_norm[i]
        with torch.no_grad():
            obs_q = model(obs_q_norm.unsqueeze(0))[0]
        best_action = obs_q.argmax().item()
        baseline_q[best_action].item()
        full_val = obs_q[best_action].item()

        for f in range(STATE_DIM):
            perturbed = obs_q_norm.clone()
            perturbed[f] = ref_norm[:, f].mean()
            with torch.no_grad():
                perturbed_q = model(perturbed.unsqueeze(0))[0, best_action].item()
            shap_values[i, f] = full_val - perturbed_q

    return shap_values

def gaussian_kernel_shap(  # noqa: N803
    model, mean, std, X_sample, X_ref, n_background=50, n_obs=20, n_perturb=200  # noqa: N803
):
    """
    More accurate KernelSHAP-style approach using Gaussian reference.
    Samples perturbations in feature subspace instead of simple mean replacement.
    """
    X_sample_t = torch.FloatTensor(X_sample)  # noqa: N806
    ref_t = torch.FloatTensor(X_ref[:n_background])

    X_norm = (X_sample_t - mean) / (std + 1e-6)  # noqa: N806
    ref_norm = (ref_t - mean) / (std + 1e-6)

    with torch.no_grad():
        model(ref_norm).mean(dim=0)

    n_obs = min(len(X_sample), n_obs)
    shap_values = np.zeros((n_obs, STATE_DIM))

    for i in range(n_obs):
        obs_q = model(X_norm[i].unsqueeze(0))[0]
        best_action = obs_q.argmax().item()

        for f in range(STATE_DIM):
            # Monte Carlo: sample from reference distribution for this feature
            perturbed = X_norm[i].unsqueeze(0).repeat(n_perturb, 1)
            perturbed[:, f] = ref_norm[torch.randint(0, len(ref_norm), (n_perturb,)), f]
            with torch.no_grad():
                perturbed_q = model(perturbed)[:, best_action]
            shap_values[i, f] = obs_q[best_action].item() - perturbed_q.mean().item()

    return shap_values


def analyze_shap_results(shap_vals, feature_names, model_name):
    """Analyze and print SHAP results."""
    mean_abs = np.abs(shap_vals).mean(axis=0)
    mean_raw = shap_vals.mean(axis=0)
    norm_importance = mean_abs / mean_abs.sum()

    # Group features
    edge_features = ["edge_front", "edge_back", "edge_left"]
    position_features = ["robot_x", "robot_y"]
    opponent_features = ["opponent_x", "opponent_y"]

    edge_importance = sum(norm_importance[feature_names.index(f)] for f in edge_features)
    pos_importance = sum(norm_importance[feature_names.index(f)] for f in position_features)
    opp_importance = sum(norm_importance[feature_names.index(f)] for f in opponent_features)

    print(f"\n{'=' * 60}")
    print(f" SHAP FEATURE IMPORTANCE — {model_name}")
    print(f"{'=' * 60}")
    print(f"  {'Feature':<18s} | {'Abs SHAP':>10s} | {'Normalized':>10s} | {'Direction':>10s}")
    print(f"  {'-' * 18}-+-{'-' * 10}-+-{'-' * 10}-+-{'-' * 10}")

    ranking = sorted(enumerate(norm_importance), key=lambda x: -x[1])
    for _rank, (feat_idx, imp) in enumerate(ranking):
        direction = "UP" if mean_raw[feat_idx] > 0 else "DOWN"
        print(
            f"  {feature_names[feat_idx]:<18s} | {mean_abs[feat_idx]:>10.4f} | {imp:>10.3f} | {direction:>10s}"
        )

    print("\n  -- Feature Groups --")
    print(f"  Edge features:      {edge_importance:.1%}")
    print(f"  Robot position:     {pos_importance:.1%}")
    print(
        f"  Opponent position:  {opp_importance:.1%} {'[OK] >10% threshold' if opp_importance >= 0.10 else '[FAIL] <10% threshold'}"
    )

    # Opponent vs Robot ratio
    if pos_importance > 0:
        ratio = opp_importance / pos_importance
        print(
            f"  Opponent/Robot ratio: {ratio:.2f} {'Balanced' if 0.5 <= ratio <= 2.0 else 'WARNING: Imbalanced'}"
        )

    return {
        "model": model_name,
        "mean_abs_shap": mean_abs.tolist(),
        "mean_raw_shap": mean_raw.tolist(),
        "normalized_importance": norm_importance.tolist(),
        "edge_importance": float(edge_importance),
        "robot_position_importance": float(pos_importance),
        "opponent_position_importance": float(opp_importance),
        "opponent_above_10pct": opp_importance >= 0.10,
        "ranking": [
            {
                "rank": i + 1,
                "feature": feature_names[idx],
                "importance": float(norm_importance[idx]),
            }
            for i, (idx, _) in enumerate(ranking)
        ],
    }


def main():
    print("=" * 60)
    print(" SHAP Analysis: Nano V2 (Opponent-Aware Distilled)")
    print("=" * 60)

    # -- Load both models --
    v2_path = os.path.join(MODEL_DIR, "nano_student_v2.pt")
    v1_path = os.path.join(MODEL_DIR, "nano_student.pt")

    if not os.path.exists(v2_path):
        print(f"  [ERR] V2 model not found: {v2_path}")
        print("  Checking for distill_nano_v2.py output...")
        alt_path = "models/nano_student_v2.pt"
        if os.path.exists(alt_path):
            v2_path = alt_path
        else:
            return {"error": "nano_student_v2.pt not found"}

    has_v1 = os.path.exists(v1_path)
    if not has_v1:
        v1_path_alt = "models/nano_student.pt"
        if os.path.exists(v1_path_alt):
            v1_path = v1_path_alt
            has_v1 = True

    print(f"  V2 model: {v2_path}")
    print(f"  V1 model: {v1_path} {'[OK]' if has_v1 else '[MISSING (will skip V1 comparison)]'}")

    v2_model, v2_mean, v2_std = load_model(v2_path, "Nano-V2")

    # -- Collect observations --
    print("\n  Collecting V2 observations...")
    X_v2, action_dist_v2 = collect_observations(v2_model, v2_mean, v2_std, n_samples=500)  # noqa: N806
    print(f"  Collected: {len(X_v2)} samples")

    # -- Background reference --
    np.random.seed(42)
    ref_idx = np.random.choice(len(X_v2), min(80, len(X_v2)), replace=False)
    X_ref = X_v2[ref_idx]  # noqa: N806

    # -- Run perturbation SHAP --
    print("\n  Computing per-feature perturbation SHAP...")
    t0 = time.time()
    shap_v2 = perturbation_shap(v2_model, v2_mean, v2_std, X_v2, X_ref, n_background=50, n_obs=100)
    t_pert = time.time() - t0
    print(f"  Perturbation SHAP: {t_pert:.1f}s")

    # -- Run Gaussian kernel SHAP (more accurate) --
    print("\n  Computing Gaussian Kernel SHAP...")
    t0 = time.time()
    shap_v2_gauss = gaussian_kernel_shap(
        v2_model, v2_mean, v2_std, X_v2, X_ref, n_background=50, n_obs=20, n_perturb=200
    )
    t_gauss = time.time() - t0
    print(f"  Gaussian SHAP: {t_gauss:.1f}s")

    # -- Analyze V2 results --
    result_pert = analyze_shap_results(shap_v2, FEATURE_NAMES, "Nano-V2 (Perturbation)")
    result_gauss = analyze_shap_results(shap_v2_gauss, FEATURE_NAMES, "Nano-V2 (Gaussian)")

    # -- V1 comparison (if available) --
    result_v1 = None
    if has_v1:
        print(f"\n{'=' * 60}")
        print(" V1 BASELINE COMPARISON")
        print(f"{'=' * 60}")

        v1_model, v1_mean, v1_std = load_model(v1_path, "Nano-V1")

        print("  Collecting V1 observations...")
        X_v1, action_dist_v1 = collect_observations(v1_model, v1_mean, v1_std, n_samples=500)  # noqa: N806

        np.random.seed(42)
        ref_idx_v1 = np.random.choice(len(X_v1), min(80, len(X_v1)), replace=False)
        X_ref_v1 = X_v1[ref_idx_v1]  # noqa: N806

        shap_v1 = perturbation_shap(
            v1_model, v1_mean, v1_std, X_v1, X_ref_v1, n_background=50, n_obs=100
        )
        result_v1 = analyze_shap_results(shap_v1, FEATURE_NAMES, "Nano-V1 (Baseline)")

    # -- V1 vs V2 comparison --
    if result_v1 and result_pert:
        print(f"\n{'=' * 60}")
        print(" V1 → V2 OPPONENT FEATURE PRESERVATION CHECK")
        print(f"{'=' * 60}")

        opp_v1 = result_v1["opponent_position_importance"]
        opp_v2 = result_pert["opponent_position_importance"]
        opp_v2_g = result_gauss["opponent_position_importance"]

        delta_pert = opp_v2 - opp_v1
        delta_gauss = opp_v2_g - opp_v1

        print(f"  V1 opponent importance:  {opp_v1:.1%}")
        print(f"  V2 opponent importance:  {opp_v2:.1%} (perturbation), {opp_v2_g:.1%} (gaussian)")
        print(f"  (perturbation):        {delta_pert:+.1%}")
        print(f"  (gaussian):            {delta_gauss:+.1%}")

        if opp_v2 >= 0.10 or opp_v2_g >= 0.10:
            print("  >>> VERDICT: Opponent features preserved above 10% threshold!")
            print("     lambda=0.3 opponent correlation loss was effective.")
        else:
            print("  <<< VERDICT: Opponent features still below 10% threshold.")
            if opp_v2 > opp_v1:
                print(f"     Small improvement ({delta_pert:+.1%}) but insufficient.")
                print("     λ=0.3 was too small relative to hard loss (~2250).")
                print(
                    "     Recommendation: increase λ to 3.0-5.0 or use feature-wise distillation."
                )
            else:
                print("     No improvement — opponent_correlation_loss had no effect.")
                print("     Recommendation: redesign loss with per-feature Q-value alignment.")

    # -- Save results --
    full_result = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "v2_perturbation": result_pert,
        "v2_gaussian": result_gauss,
        "method_notes": {
            "perturbation": "Per-feature mean replacement, n=100 samples",
            "gaussian": "Gaussian kernel SHAP with MC sampling, n=20 samples × 200 perturbations",
        },
    }
    if result_v1:
        full_result["v1_baseline"] = result_v1
        full_result["comparison"] = {
            "v1_opponent_importance": opp_v1,
            "v2_opponent_importance_perturbation": opp_v2,
            "v2_opponent_importance_gaussian": opp_v2_g,
            "delta_perturbation": delta_pert,
            "delta_gaussian": delta_gauss,
            "threshold_met_perturbation": bool(opp_v2 >= 0.10),
            "threshold_met_gaussian": bool(opp_v2_g >= 0.10),
        }

    result_path = os.path.join(RESULTS_DIR, "shap_nano_v2_results.json")
    with open(result_path, "w") as f:
        json.dump(full_result, f, indent=2)

    print(f"\n  [Results saved: {result_path}]")
    return full_result


if __name__ == "__main__":
    main()
