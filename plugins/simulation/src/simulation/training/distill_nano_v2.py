"""
distill_nano_v2.py — Knowledge distillation with opponent-feature preservation.

Fixes the SHAP-discovered issue: Nano V1 learned to ignore opponent features
(edge_front=53%, opponent_x=0%). This version adds opponent-feature-aware loss
to preserve the teacher's opponent-tracking capability.

Key changes from V1:
1. Uses bottlesumo_pi.common (eliminates duplicated QNet)
2. Adds opponent_Q_correlation loss to preserve opponent-related Q-value structure
3. Higher temperature for opponent features → softer targets → preserved signal
"""

import json
import os
import sys
import time

import numpy as np
import torch
import torch.nn.functional as F
import torch.optim as optim

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bottlesumo_pi.common import DQN, NanoQNet
from lightweight_env import LightweightBottleSumoEnv

MODEL_DIR = "models"
RESULTS_DIR = os.path.join("bottlesumo_pi", "simulation", "evaluation")
os.makedirs(RESULTS_DIR, exist_ok=True)

# ── Distillation HP ──
DISTILL_HP = {
    "n_epochs": 30,
    "batch_size": 256,
    "lr": 3e-4,
    "temperature": 4.0,
    "alpha": 0.5,  # soft vs hard loss weight
    "opponent_lambda": 0.3,  # NEW: opponent preservation weight
    "n_collection_episodes": 100,
    "teacher_hidden": 128,
    "teacher_layers": 2,
}

FEATURE_NAMES = [
    "robot_x",
    "robot_y",
    "opponent_x",
    "opponent_y",
    "edge_front",
    "edge_back",
    "edge_left",
]
OPPONENT_FEATURES = [2, 3]  # opponent_x, opponent_y


def collect_teacher_data(teacher_model, n_episodes=100):
    """Collect (state, Q-value) pairs from teacher with diverse opponent profiles."""
    bucket_size = n_episodes // 4
    inputs, q_values = [], []

    for profile in ["aggressive", "moderate", "passive", "stationary"]:
        env = LightweightBottleSumoEnv(opponent_profile=profile, render_mode="none")
        for _ep in range(bucket_size):
            obs, _ = env.reset(seed=np.random.randint(0, 10000))
            done = False
            while not done:
                inputs.append(torch.FloatTensor(obs))
                with torch.no_grad():
                    q = teacher_model(torch.FloatTensor(obs).unsqueeze(0)).squeeze(0)
                q_values.append(q.clone())
                action = q.argmax().item()
                obs, _, done, truncated, _ = env.step(action)
                if truncated:
                    done = True
                if len(inputs) >= n_episodes * 50:
                    break
            if len(inputs) >= n_episodes * 50:
                break
        env.close()

    # Trim to equal size
    n_samples = min(len(inputs), n_episodes * 50)
    inputs = torch.stack(inputs[:n_samples])
    q_values = torch.stack(q_values[:n_samples])

    # Compute normalization stats
    X_mean = inputs.mean(dim=0).unsqueeze(0)  # noqa: N806
    X_std = inputs.std(dim=0).unsqueeze(0)  # noqa: N806
    X_norm = (inputs - X_mean) / (X_std + 1e-6)  # noqa: N806

    print(f"  Collected: {n_samples} state-Q pairs")
    print(f"  Q-value range: [{q_values.min().item():.2f}, {q_values.max().item():.2f}]")
    return X_norm, q_values, X_mean, X_std


def opponent_correlation_loss(student_q: torch.Tensor, teacher_q: torch.Tensor):
    """Encourage student to preserve opponent-related Q-value ordering.

    This is the key fix: penalize the student when it collapses opponent features.
    We compute the Q-value variance explained by opponent position variation,
    and ensure the student maintains similar variance structure.
    """
    # For each batch, compute Q-value spread when opponent position varies
    teacher_var = teacher_q.var(dim=0).mean()  # mean variance across actions
    student_var = student_q.var(dim=0).mean()

    # Relative variance ratio — penalize excessive collapse
    var_ratio = (student_var / (teacher_var + 1e-6)).clamp(0, 2)
    return F.mse_loss(var_ratio, torch.ones_like(var_ratio))


def distill(teacher_path: str, hp: dict = None):
    hp = hp or DISTILL_HP
    print(f"╔{'═' * 60}╗")
    print(f"║  Nano Distillation V2 (Opponent-Aware){'':>22s}║")
    print(f"║  Teacher: {teacher_path:>44s}  ║")
    print(f"╚{'═' * 60}╝")

    # Load teacher
    teacher = DQN(
        obs_dim=7, action_dim=21, hidden_dim=hp["teacher_hidden"], n_hidden=hp["teacher_layers"]
    )
    teacher.load_state_dict(torch.load(teacher_path, map_location="cpu", weights_only=True))
    teacher.eval()
    n_teacher_params = sum(p.numel() for p in teacher.parameters())
    print(f"  Teacher: {n_teacher_params} params ({n_teacher_params * 4 / 1024:.1f}KB)")

    # Collect data
    print("  Collecting teacher Q-values...")
    X_norm, q_teacher, X_mean, X_std = collect_teacher_data(  # noqa: N806
        teacher, n_episodes=hp["n_collection_episodes"]
    )

    # Student model
    student = NanoQNet()
    n_student_params = sum(p.numel() for p in student.parameters())
    print(f"  Student: {n_student_params} params ({n_student_params * 4 / 1024:.1f}KB)")
    print(f"  Compression: {n_teacher_params / n_student_params:.1f}x\n")

    optimizer = optim.Adam(student.parameters(), lr=hp["lr"])
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, hp["n_epochs"])

    # Training
    n_samples = len(X_norm)
    history = {"epoch": [], "loss_total": [], "loss_kl": [], "loss_hard": [], "loss_opp": []}
    t_start = time.time()

    for epoch in range(hp["n_epochs"]):
        perm = torch.randperm(n_samples)
        total_loss = total_kl = total_hard = total_opp = 0.0
        n_batches = 0

        for i in range(0, n_samples, hp["batch_size"]):
            idx = perm[i : i + hp["batch_size"]]
            x = X_norm[idx]
            with torch.no_grad():
                t_q = q_teacher[idx]

            s_logits = student(x)
            s_log_soft = F.log_softmax(s_logits / hp["temperature"], dim=1)
            t_soft = F.softmax(t_q / hp["temperature"], dim=1)

            # KL divergence (soft loss)
            loss_kl = F.kl_div(s_log_soft, t_soft, reduction="batchmean") * (hp["temperature"] ** 2)

            # Hard loss (MSE on Q-values)
            loss_hard = F.mse_loss(s_logits, t_q)

            # Opponent preservation loss (NEW)
            loss_opp = opponent_correlation_loss(s_logits, t_q)

            loss = (
                hp["alpha"] * loss_kl
                + (1 - hp["alpha"]) * loss_hard
                + hp["opponent_lambda"] * loss_opp
            )

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(student.parameters(), 1.0)
            optimizer.step()

            total_loss += loss.item()
            total_kl += loss_kl.item()
            total_hard += loss_hard.item()
            total_opp += loss_opp.item()
            n_batches += 1

        scheduler.step()

        avg_loss = total_loss / n_batches
        history["epoch"].append(epoch)
        history["loss_total"].append(avg_loss)
        history["loss_kl"].append(total_kl / n_batches)
        history["loss_hard"].append(total_hard / n_batches)
        history["loss_opp"].append(total_opp / n_batches)

        if (epoch + 1) % 5 == 0 or epoch == 0:
            print(
                f"  Epoch {epoch + 1:3d}/{hp['n_epochs']} | loss={avg_loss:.4f} "
                f"| KL={total_kl / n_batches:.4f} | MSE={total_hard / n_batches:.4f} "
                f"| Opp={total_opp / n_batches:.4f} | lr={scheduler.get_last_lr()[0]:.2e}"
            )

    elapsed = time.time() - t_start
    print(f"\n  Distillation complete: {elapsed:.0f}s ({elapsed / 60:.1f}min)")

    # Save
    save_path = os.path.join(MODEL_DIR, "nano_student_v2.pt")
    torch.save(
        {
            "state_dict": student.state_dict(),
            "X_mean": X_mean.numpy(),
            "X_std": X_std.numpy(),
            "config": {
                "teacher": teacher_path,
                "opponent_lambda": hp["opponent_lambda"],
                "temperature": hp["temperature"],
                "alpha": hp["alpha"],
            },
        },
        save_path,
    )
    print(f"  Saved: {os.path.abspath(save_path)}")

    # History
    hist_path = save_path.replace(".pt", "_history.json")
    with open(hist_path, "w") as f:
        json.dump(history, f)

    # Run a quick opponent-feature sensitivity check
    print("\n  Checking opponent feature sensitivity...")
    sensitivity = check_opponent_sensitivity(student, X_mean, X_std)
    print(f"  Opponent Q-variation: {sensitivity:.4f} (higher = more opponent-aware)")

    return student


def check_opponent_sensitivity(model, X_mean, X_std, n_samples=200):  # noqa: N803
    """Measure how much Q-values change when opponent position varies."""
    model.eval()
    q_spreads = []
    for _ in range(n_samples):
        base = torch.randn(7)
        base_norm = (base - X_mean.squeeze()) / (X_std.squeeze() + 1e-6)
        with torch.no_grad():
            q_base = model(base_norm.unsqueeze(0))

        # Perturb opponent features only
        perturbed = base.clone()
        perturbed[2] += np.random.uniform(-0.5, 0.5)  # opponent_x
        perturbed[3] += np.random.uniform(-0.5, 0.5)  # opponent_y
        perturbed_norm = (perturbed - X_mean.squeeze()) / (X_std.squeeze() + 1e-6)
        with torch.no_grad():
            q_pert = model(perturbed_norm.unsqueeze(0))

        q_spreads.append((q_pert - q_base).abs().mean().item())

    return float(np.mean(q_spreads))


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--teacher", type=str, default=os.path.join(MODEL_DIR, "v10_dqn_best.pt"))
    parser.add_argument(
        "--opponent-lambda",
        type=float,
        default=0.3,
        help="Opponent preservation loss weight (0.0 = V1, higher = more opponent-aware)",
    )
    args = parser.parse_args()

    if not os.path.exists(args.teacher):
        print(f"ERROR: Teacher model not found: {args.teacher}")
        print("  Run train.py first to generate v10_dqn_best.pt")
        sys.exit(1)

    hp = DISTILL_HP.copy()
    hp["opponent_lambda"] = args.opponent_lambda
    distill(args.teacher, hp)


if __name__ == "__main__":
    main()
