"""
distill_nano_v3.py — V3 Opponent-aware distillation with paired Q-difference loss.

Root cause of V2 failure:
  1. Environment lacks opponent diversity (all positions ~0.999±0.005)
  2. V2's opponent_correlation_loss matched OUTPUT VARIANCE, not FEATURE sensitivity
  3. λ=0.3 was drown by MSE~4500 (0.0067% contribution)

V3 key innovation: PAIRED Q-DIFFERENCE MATCHING
  For each synthetic state, generate a "twin" with identical robot/edges but
  different opponent position. Compare ΔQ between twin pair for teacher and student.
  This DIRECTLY measures opponent sensitivity — not confounded by state quality.
"""

import json
import os
import sys
import time

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim

_PROJ_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
sys.path.insert(0, _PROJ_ROOT)

from bottlesumo_pi.common import DQN, NanoQNet  # noqa: E402
from lightweight_env import LightweightBottleSumoEnv  # noqa: E402

MODEL_DIR = os.path.join(_PROJ_ROOT, "models")
os.makedirs(MODEL_DIR, exist_ok=True)

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

HP = {
    "n_epochs": 60,
    "batch_size": 256,
    "lr": 5e-5,
    "temperature": 5.0,
    "alpha": 0.7,  # KD weighting (soft vs hard)
    "opponent_lambda": 0.5,  # Paired Q-diff loss weight
    "n_base_states": 2000,  # Unique base states (each with 4 opponent twins)
    "teacher_hidden": 128,
    "teacher_layers": 2,
    "grad_clip": 1.0,
    "lr_decay": 0.98,
}


def generate_paired_states(teacher_model, n_base=2000, n_twins=4, arena_radius=0.95):
    """
    Generate base states with opponent-twins.
    Each base state spawns n_twins with different opponent positions but SAME
    robot position and edge features.

    Returns:
        states: [n_base * (1 + n_twins), 7]  (original + twins)
        q_values: [n_base * (1 + n_twins), 21]
        pair_idx: [(base_idx, twin_idx), ...] for loss computation
    """
    print(f"  Generating {n_base} base states x {n_twins} opponents...")

    center = 1.0
    max_r = arena_radius

    all_states = []
    pairs = []

    for _i in range(n_base):
        # Random robot position
        r_angle = np.random.uniform(0, 2 * np.pi)
        r_radius = np.random.uniform(0, max_r)
        robot_x = center + r_radius * np.cos(r_angle)
        robot_y = center + r_radius * np.sin(r_angle)

        # Edge features from robot position
        edge_front = np.clip(robot_y, 0.02, 2.0)
        edge_back = np.random.uniform(0.5, 2.0)
        edge_left = np.clip(robot_x, 0.02, 2.0)

        # Generate n_twins + 1 different opponent positions
        opponent_positions = []
        for _t in range(n_twins + 1):
            for _attempt in range(100):
                o_angle = np.random.uniform(0, 2 * np.pi)
                o_radius = np.random.uniform(0, max_r)
                ox = center + o_radius * np.cos(o_angle)
                oy = center + o_radius * np.sin(o_angle)
                # Ensure separation from robot
                if np.hypot(ox - robot_x, oy - robot_y) > 0.05:
                    opponent_positions.append((ox, oy))
                    break

        # Create states
        base_idx = len(all_states)
        for _t, (ox, oy) in enumerate(opponent_positions):
            state = np.array(
                [robot_x, robot_y, ox, oy, edge_front, edge_back, edge_left], dtype=np.float32
            )
            all_states.append(state)

        # Record pairs: base (t=0) vs each twin (t=1..n_twins)
        for t in range(1, n_twins + 1):
            pairs.append((base_idx, base_idx + t))

    states = np.array(all_states)
    n_total = len(states)

    # Batch-compute teacher Q-values
    print(f"  Computing teacher Q-values for {n_total} states...")
    q_values = np.zeros((n_total, N_ACTIONS), dtype=np.float32)
    bs = 512
    for i in range(0, n_total, bs):
        batch = torch.FloatTensor(states[i : i + bs])
        with torch.no_grad():
            q_values[i : i + bs] = teacher_model(batch).numpy()

    print(f"  Generated {n_total} states, {len(pairs)} pairs for Q-diff loss")
    return states, q_values, pairs


def collect_real_data(teacher_model, n_episodes=40):
    """Collect environment data as regularization signal."""
    bucket_size = n_episodes // 4
    inputs, q_list = [], []
    for profile in ["aggressive", "moderate", "passive", "stationary"]:
        env = LightweightBottleSumoEnv(opponent_profile=profile, render_mode="none")
        for _ep in range(bucket_size):
            obs, _ = env.reset(seed=np.random.randint(0, 10000))
            done, step = False, 0
            while not done and step < 100:
                inputs.append(torch.FloatTensor(obs))
                with torch.no_grad():
                    q_list.append(teacher_model(torch.FloatTensor(obs).unsqueeze(0)).squeeze(0))
                action = q_list[-1].argmax().item()
                obs, _, done, truncated, _ = env.step(action)
                if truncated:
                    done = True
                step += 1
        env.close()
    return torch.stack(inputs), torch.stack(q_list)


def paired_qdiff_loss(student_q, teacher_q, pair_indices):
    """
    For each (base, twin) pair, compare ΔQ between teacher and student.

    ΔQ_teacher(s_base, s_twin) = teacher_Q(s_twin) - teacher_Q(s_base)
    ΔQ_student(s_base, s_twin) = student_Q(s_twin) - student_Q(s_base)

    Loss = MSE(ΔQ_student, ΔQ_teacher) across all pairs and actions.

    This directly measures: "does the student track opponent changes the same way
    the teacher does?"
    """
    if len(pair_indices) == 0:
        return torch.tensor(0.0, device=student_q.device)

    base_idx = torch.tensor([p[0] for p in pair_indices], dtype=torch.long, device=student_q.device)
    twin_idx = torch.tensor([p[1] for p in pair_indices], dtype=torch.long, device=student_q.device)

    # Get Q-values for base and twin states
    s_base = student_q[base_idx]  # [P, 21]
    s_twin = student_q[twin_idx]  # [P, 21]
    t_base = teacher_q[base_idx]  # [P, 21]
    t_twin = teacher_q[twin_idx]  # [P, 21]

    # Q-differences
    ΔQ_student = s_twin - s_base  # [P, 21]  # noqa: N806
    ΔQ_teacher = t_twin - t_base  # [P, 21]  # noqa: N806

    # MSE over all (pair, action) dimensions
    return F.mse_loss(ΔQ_student, ΔQ_teacher.detach())


def distill_nano_v3(teacher_path, hp=None):
    hp = hp or HP

    print("=" * 60)
    print("  Nano Distillation V3: Paired Q-Difference Matching")
    print("=" * 60)
    print(f"  Teacher: {teacher_path}")
    print(f"  lambda_opp: {hp['opponent_lambda']}")
    print(f"  T: {hp['temperature']}, alpha: {hp['alpha']}")

    # Load teacher
    teacher = DQN(
        obs_dim=STATE_DIM,
        action_dim=N_ACTIONS,
        hidden_dim=hp["teacher_hidden"],
        n_hidden=hp["teacher_layers"],
    )
    teacher_ckpt = torch.load(teacher_path, map_location="cpu", weights_only=False)
    teacher.load_state_dict(teacher_ckpt.get("state_dict", teacher_ckpt))
    teacher.eval()
    print(f"  Teacher: {sum(p.numel() for p in teacher.parameters()):,} params")

    # Generate paired data
    synth_states, synth_q, pair_indices = generate_paired_states(
        teacher, n_base=hp["n_base_states"], n_twins=4
    )

    # Collect real data
    print("  Collecting environment data...")
    real_states, real_q = collect_real_data(teacher, n_episodes=40)
    print(f"  Real samples: {len(real_states)}")

    # Combine and normalize
    all_states = torch.cat([torch.FloatTensor(synth_states), real_states], dim=0)
    all_q = torch.cat([torch.FloatTensor(synth_q), real_q], dim=0)

    X_mean = all_states.mean(dim=0).clamp(min=0.001)  # noqa: N806
    X_std = all_states.std(dim=0).clamp(min=0.001)  # noqa: N806
    X_norm = (all_states - X_mean) / (X_std + 1e-6)  # noqa: N806

    n_synth = len(synth_states)

    print(
        f"\n  Total data: {len(all_states)} samples ({n_synth} synthetic + {len(real_states)} real)"
    )
    print("  Normalization:")
    for i, name in enumerate(FEATURE_NAMES):
        print(f"    {name:<14s}: mean={X_mean[i]:.4f}, std={X_std[i]:.4f}")
    print(f"  Q range: [{all_q.min():.1f}, {all_q.max():.1f}]")
    print(f"  Paired Q-diff pairs: {len(pair_indices)}")

    # ── Student ──
    student = NanoQNet()
    print(f"\n  Student: {sum(p.numel() for p in student.parameters())} params")

    optimizer = optim.AdamW(student.parameters(), lr=hp["lr"], weight_decay=1e-5)

    history = []
    n_samples = len(X_norm)
    t_start = time.time()

    for epoch in range(hp["n_epochs"]):
        perm = torch.randperm(n_samples)
        epoch_losses = {"total": 0, "kl": 0, "mse": 0, "opp": 0}
        n_batches = 0
        all_s_q = []

        # ── Batch training loop ──
        for i in range(0, n_samples, hp["batch_size"]):
            idx = perm[i : i + hp["batch_size"]]
            x = X_norm[idx]
            t_q = all_q[idx]

            s_logits = student(x)

            # KL (soft distillation)
            s_log_soft = F.log_softmax(s_logits / hp["temperature"], dim=1)
            t_soft = F.softmax(t_q / hp["temperature"], dim=1)
            loss_kl = F.kl_div(s_log_soft, t_soft, reduction="batchmean") * (hp["temperature"] ** 2)

            # MSE (hard distillation)
            loss_mse = F.mse_loss(s_logits, t_q)

            loss = hp["alpha"] * loss_kl + (1 - hp["alpha"]) * loss_mse

            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(student.parameters(), hp["grad_clip"])
            optimizer.step()

            epoch_losses["total"] += loss.item()
            epoch_losses["kl"] += loss_kl.item()
            epoch_losses["mse"] += loss_mse.item()
            n_batches += 1
            all_s_q.append(s_logits.detach())

        # ── Paired Q-difference loss (computed once per epoch on all synthetic data) ──
        pair_states = X_norm[:n_synth]
        pair_teacher_q = all_q[:n_synth]

        # Sample pairs for efficiency
        if len(pair_indices) > 1024:
            sample_pairs = [
                pair_indices[j] for j in np.random.choice(len(pair_indices), 1024, replace=False)
            ]
        else:
            sample_pairs = pair_indices

        s_q_synth = student(pair_states)
        loss_opp = paired_qdiff_loss(s_q_synth, pair_teacher_q, sample_pairs)

        if loss_opp.item() > 0:
            optimizer.zero_grad()
            (hp["opponent_lambda"] * loss_opp).backward()
            nn.utils.clip_grad_norm_(student.parameters(), hp["grad_clip"])
            optimizer.step()

        epoch_losses["opp"] = loss_opp.item()
        epoch_losses["total"] += hp["opponent_lambda"] * loss_opp.item()

        for k in epoch_losses:
            epoch_losses[k] /= n_batches

        # Action diversity
        all_s_q_t = torch.cat(all_s_q, dim=0)
        actions = all_s_q_t[: min(2000, len(all_s_q_t))].argmax(dim=1)
        div = len(torch.unique(actions))
        q_var = all_s_q_t.var().item()

        opp_pct = (
            hp["opponent_lambda"] * epoch_losses["opp"] / (epoch_losses["total"] + 1e-10)
        ) * 100

        history.append(
            {
                "epoch": epoch,
                "loss_total": epoch_losses["total"],
                "loss_kl": epoch_losses["kl"],
                "loss_mse": epoch_losses["mse"],
                "loss_opp": epoch_losses["opp"],
                "opp_pct": opp_pct,
                "action_diversity": div,
                "q_variance": q_var,
            }
        )

        if epoch % 10 == 0 or epoch == 0:
            print(
                f"  Ep {epoch:3d} | total={epoch_losses['total']:.2f} "
                f"KL={epoch_losses['kl']:.4f} MSE={epoch_losses['mse']:.2f} "
                f"OPP={epoch_losses['opp']:.4f} ({opp_pct:.1f}%) "
                f"div={div}/21 q_var={q_var:.4f}"
            )

    elapsed = time.time() - t_start
    print(f"\n  Training: {elapsed:.0f}s ({elapsed / 60:.1f}min)")
    print(f"  Final diversity: {div}/21, Q-var: {q_var:.6f}")

    # ── Save ──
    save_path = os.path.join(MODEL_DIR, "nano_student_v3.pt")
    torch.save(
        {
            "state_dict": student.state_dict(),
            "X_mean": X_mean.numpy(),
            "X_std": X_std.numpy(),
            "config": {"version": "v3", "teacher": teacher_path, **{k: v for k, v in hp.items()}},
        },
        save_path,
    )

    with open(save_path.replace(".pt", "_history.json"), "w") as f:
        json.dump(history, f, indent=2)

    print(f"  Saved: {save_path}")
    return student, X_mean, X_std


if __name__ == "__main__":
    teacher = os.path.join(MODEL_DIR, "v10_bayesopt_dqn.pt")
    if not os.path.exists(teacher):
        teacher = os.path.join(MODEL_DIR, "v10_dqn_best.pt")
    distill_nano_v3(teacher)
