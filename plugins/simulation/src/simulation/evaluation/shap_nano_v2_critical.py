"""
shap_nano_v2_critical.py -- Targeted opponent feature usage test.

Instead of full SHAP (which can be sensitive to perturbation scale),
directly tests: "Does the model's Q-values change when opponent position
changes but everything else stays the same?"
"""

import json
import os
import sys

import numpy as np

_PROJ_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
sys.path.insert(0, _PROJ_ROOT)

import torch  # noqa: E402
import torch.nn as nn  # noqa: E402

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
    mean = torch.FloatTensor(ckpt["X_mean"][0])
    std = torch.FloatTensor(ckpt["X_std"][0])
    return model, mean, std


def test_opponent_sensitivity(model, mean, std, n_samples=200, name="Model"):
    """
    Critical test: Given N random valid states, measure how Q-values change
    when opponent position is randomly varied.

    Creates pairs: (state, state_with_randomized_opponent) and measures Q-value change.
    """
    np.random.seed(42)
    torch.manual_seed(42)

    # Generate diverse valid states (positions in radius=1.0 arena)
    # Robot near origin, opponent random, edges valid
    all_results = []

    for _i in range(n_samples):
        # Generate a base state
        robot_x = np.random.uniform(-0.3, 0.3)
        robot_y = np.random.uniform(-0.3, 0.3)
        opp_x = np.random.uniform(-0.8, 0.8)
        opp_y = np.random.uniform(-0.8, 0.8)

        # Ensure robot and opponent aren't overlapping (sanity)
        dist = np.sqrt((robot_x - opp_x) ** 2 + (robot_y - opp_y) ** 2)
        if dist < 0.1:
            continue

        # Edge distances (plausible values for a 1.0m radius arena)
        edge_front = np.random.uniform(0.05, 0.6)
        edge_back = np.random.uniform(0.05, 0.6)
        edge_left = np.random.uniform(0.05, 0.6)

        base_state = np.array(
            [robot_x, robot_y, opp_x, opp_y, edge_front, edge_back, edge_left], dtype=np.float32
        )

        # Normalize
        base_norm = (torch.FloatTensor(base_state) - mean) / (std + 1e-6)

        with torch.no_grad():
            base_q = model(base_norm.unsqueeze(0))[0]
        base_best_action = base_q.argmax().item()
        base_best_q = base_q[base_best_action].item()

        # Generate K variations with randomized opponent position
        K = 50  # noqa: N806
        q_changes = []
        action_changes = 0

        for _k in range(K):
            opp_x_rand = np.random.uniform(-0.8, 0.8)
            opp_y_rand = np.random.uniform(-0.8, 0.8)

            varied = base_state.copy()
            varied[2] = opp_x_rand
            varied[3] = opp_y_rand

            varied_norm = (torch.FloatTensor(varied) - mean) / (std + 1e-6)

            with torch.no_grad():
                varied_q = model(varied_norm.unsqueeze(0))[0]

            # Q change at original best action
            q_change = abs(varied_q[base_best_action].item() - base_best_q)
            q_changes.append(q_change)

            # Action change
            if varied_q.argmax().item() != base_best_action:
                action_changes += 1

        all_results.append(
            {
                "base_state": base_state.tolist(),
                "base_best_action": base_best_action,
                "base_best_q": base_best_q,
                "mean_q_change": float(np.mean(q_changes)),
                "max_q_change": float(np.max(q_changes)),
                "action_change_rate": float(action_changes / K),
            }
        )

    # Summary
    mean_q_changes = [r["mean_q_change"] for r in all_results]
    mean_action_changes = [r["action_change_rate"] for r in all_results]

    print(f"\n{'=' * 60}")
    print(f" OPPONENT SENSITIVITY TEST -- {name}")
    print(f"{'=' * 60}")
    print(f"  Samples tested:        {len(all_results)}")
    print(f"  Mean Q-change (all):   {np.mean(mean_q_changes):.6f}")
    print(f"  Max Q-change:          {np.max(mean_q_changes):.6f}")
    print(
        f"  Q-changes > 0.01:      {sum(1 for x in mean_q_changes if x > 0.01)}/{len(mean_q_changes)} ({sum(1 for x in mean_q_changes if x > 0.01) / len(mean_q_changes) * 100:.1f}%)"
    )
    print(f"  Mean action swap rate: {np.mean(mean_action_changes):.3f}")
    print(
        f"  Action swaps > 0%:     {sum(1 for x in mean_action_changes if x > 0)}/{len(mean_action_changes)} ({sum(1 for x in mean_action_changes if x > 0) / len(mean_action_changes) * 100:.1f}%)"
    )

    if np.mean(mean_q_changes) < 0.001:
        print("  [FAIL] Model is OPPONENT-BLIND: Q-values don't respond to opponent position")
    elif np.mean(mean_q_changes) < 0.01:
        print("  [WARN] Weak opponent sensitivity: Q changes are very small")
    else:
        print("  [OK] Model responds to opponent position")

    return {
        "name": name,
        "n_samples": len(all_results),
        "mean_q_change": float(np.mean(mean_q_changes)),
        "std_q_change": float(np.std(mean_q_changes)),
        "mean_action_change_rate": float(np.mean(mean_action_changes)),
        "pct_with_q_change_gt_001": float(
            sum(1 for x in mean_q_changes if x > 0.01) / len(mean_q_changes)
        ),
        "pct_with_action_change": float(
            sum(1 for x in mean_action_changes if x > 0) / len(mean_action_changes)
        ),
        "verdict": "BLIND"
        if np.mean(mean_q_changes) < 0.001
        else ("WEAK" if np.mean(mean_q_changes) < 0.01 else "RESPONSIVE"),
        "samples": all_results[:5],  # first 5 for reference
    }


def test_edge_vs_opponent_importance(model, mean, std, n_samples=200, name="Model"):
    """
    Direct A/B test: Compare Q-value impact of varying edge distances vs opponent position.
    This avoids the normalization scale issue that affects SHAP perturbation magnitude.
    """
    np.random.seed(42)
    torch.manual_seed(42)

    edge_changes = []
    opp_changes = []

    for _i in range(n_samples):
        robot_x = np.random.uniform(-0.3, 0.3)
        robot_y = np.random.uniform(-0.3, 0.3)
        opp_x = np.random.uniform(-0.8, 0.8)
        opp_y = np.random.uniform(-0.8, 0.8)
        dist = np.sqrt((robot_x - opp_x) ** 2 + (robot_y - opp_y) ** 2)
        if dist < 0.1:
            continue

        edge_front = np.random.uniform(0.05, 0.6)
        edge_back = np.random.uniform(0.05, 0.6)
        edge_left = np.random.uniform(0.05, 0.6)

        base_state = np.array(
            [robot_x, robot_y, opp_x, opp_y, edge_front, edge_back, edge_left], dtype=np.float32
        )
        base_norm = (torch.FloatTensor(base_state) - mean) / (std + 1e-6)

        with torch.no_grad():
            base_q = model(base_norm.unsqueeze(0))[0]
        best_action = base_q.argmax().item()
        base_q_val = base_q[best_action].item()

        # Vary edge distances
        K = 20  # noqa: N806
        for _k in range(K):
            varied = base_state.copy()
            varied[4] = np.random.uniform(0.01, 0.95)  # edge_front varies
            varied[5] = np.random.uniform(0.01, 0.95)  # edge_back varies
            varied_norm = (torch.FloatTensor(varied) - mean) / (std + 1e-6)
            with torch.no_grad():
                varied_q = model(varied_norm.unsqueeze(0))[0]
            edge_changes.append(abs(varied_q[best_action].item() - base_q_val))

        # Vary opponent position
        for _k in range(K):
            varied = base_state.copy()
            varied[2] = np.random.uniform(-0.9, 0.9)  # opponent_x varies
            varied[3] = np.random.uniform(-0.9, 0.9)  # opponent_y varies
            varied_norm = (torch.FloatTensor(varied) - mean) / (std + 1e-6)
            with torch.no_grad():
                varied_q = model(varied_norm.unsqueeze(0))[0]
            opp_changes.append(abs(varied_q[best_action].item() - base_q_val))

    mean_edge = np.mean(edge_changes)
    mean_opp = np.mean(opp_changes)

    print(f"\n{'=' * 60}")
    print(f" EDGE vs OPPONENT IMPORTANCE -- {name}")
    print(f"{'=' * 60}")
    print(f"  Mean edge feature Q-change:     {mean_edge:.6f}")
    print(f"  Mean opponent feature Q-change: {mean_opp:.6f}")
    print(f"  Ratio (opp/edge):               {mean_opp / (mean_edge + 1e-10):.4f}")

    if mean_opp < 0.001:
        print("  [FAIL] Opponent features have NO impact on Q-values")
    elif mean_opp / (mean_edge + 1e-10) < 0.05:
        print("  [FAIL] Opponent impact is <5% of edge impact (functionally blind)")
    elif mean_opp / (mean_edge + 1e-10) < 0.20:
        print(
            f"  [WARN] Opponent impact is {mean_opp / (mean_edge + 1e-10) * 100:.1f}% of edge impact (marginal)"
        )
    else:
        print(
            f"  [OK] Opponent impact is {mean_opp / (mean_edge + 1e-10) * 100:.1f}% of edge impact"
        )

    return {
        "name": name,
        "mean_edge_q_change": float(mean_edge),
        "mean_opp_q_change": float(mean_opp),
        "ratio_opp_to_edge": float(mean_opp / (mean_edge + 1e-10)),
        "verdict": "BLIND"
        if mean_opp < 0.001
        else ("MARGINAL" if mean_opp / (mean_edge + 1e-10) < 0.05 else "RESPONSIVE"),
    }


def main():
    model_dir = os.path.join(_PROJ_ROOT, "models")
    results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))

    v2_path = os.path.join(model_dir, "nano_student_v2.pt")
    v1_path = os.path.join(model_dir, "nano_student.pt")

    results = {}

    # Test V2
    print("=" * 60)
    print(" CRITICAL OPPONENT FEATURE USAGE TEST")
    print("=" * 60)

    v2_model, v2_mean, v2_std = load_model(v2_path)
    v2_opp_sens = test_opponent_sensitivity(v2_model, v2_mean, v2_std, name="Nano-V2")
    v2_edge_opp = test_edge_vs_opponent_importance(v2_model, v2_mean, v2_std, name="Nano-V2")
    results["v2"] = {"opponent_sensitivity": v2_opp_sens, "edge_vs_opponent": v2_edge_opp}

    # Test V1
    v1_model, v1_mean, v1_std = load_model(v1_path)
    v1_opp_sens = test_opponent_sensitivity(v1_model, v1_mean, v1_std, name="Nano-V1")
    v1_edge_opp = test_edge_vs_opponent_importance(v1_model, v1_mean, v1_std, name="Nano-V1")
    results["v1"] = {"opponent_sensitivity": v1_opp_sens, "edge_vs_opponent": v1_edge_opp}

    # Summary
    print(f"\n{'=' * 60}")
    print(" FINAL VERDICT")
    print(f"{'=' * 60}")
    print(f"  V1 mean Q-change (opponent): {v1_opp_sens['mean_q_change']:.6f}")
    print(f"  V2 mean Q-change (opponent): {v2_opp_sens['mean_q_change']:.6f}")

    if v2_opp_sens["mean_q_change"] > v1_opp_sens["mean_q_change"] * 2:
        print(
            f"  [PASS] V2 opponent sensitivity is {v2_opp_sens['mean_q_change'] / max(v1_opp_sens['mean_q_change'], 1e-10):.1f}x V1"
        )
    elif v2_opp_sens["mean_q_change"] > v1_opp_sens["mean_q_change"]:
        delta_pct = (
            (v2_opp_sens["mean_q_change"] - v1_opp_sens["mean_q_change"])
            / max(v1_opp_sens["mean_q_change"], 1e-10)
            * 100
        )
        print(f"  [WARN] V2 marginal improvement: +{delta_pct:.0f}% over V1")
    else:
        print("  [FAIL] V2 NO improvement over V1")

    # Save
    result_path = os.path.join(results_dir, "shap_nano_v2_critical_results.json")
    with open(result_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  Results: {result_path}")


if __name__ == "__main__":
    main()
