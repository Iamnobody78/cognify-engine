#!/usr/bin/env python3
"""
DEBT-001 Fix v3: Behavioral Cloning + DAgger (Dataset Aggregation)

v2 result: BC acc=84.26%, closed-loop=10% → distribution shift problem.
v3 fix: DAgger — iteratively collect student trajectories, relabel with expert,
        aggregate into training set, retrain. 3 DAgger iterations.
Also: larger model [128,64], more epochs (200), gradient clipping.
"""

import math
import os
import random
import sys

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests"))
from virtual_mcu import v11_select_action

from common.action_space import (
    ACTION_MAP,
    ACTION_NAMES,
    DT,
    FRICTION,
    MAX_ANGULAR,
    MAX_SPEED,
    N_ACTIONS,
    OBS_DIM,
    RING_LIMIT,
    RING_RADIUS,
    ROBOT_RADIUS,
)

GAMMA = 0.99

class LightweightEnv:
    def __init__(self, seed=None):
        if seed is not None:
            random.seed(seed)
        self.reset()

    def reset(self):
        angle = random.uniform(0, 2 * math.pi)
        r = random.uniform(0, 0.2)
        self.robot_pos = [r * math.cos(angle), r * math.sin(angle)]
        self.robot_vel = [0.0, 0.0]
        self.heading = random.uniform(0, 2 * math.pi)
        self.angular_v = 0.0
        while True:
            angle = random.uniform(0, 2 * math.pi)
            r = random.uniform(0.3, 0.7)
            self.opp_pos = [r * math.cos(angle), r * math.sin(angle)]
            dist = math.sqrt(
                (self.opp_pos[0] - self.robot_pos[0]) ** 2
                + (self.opp_pos[1] - self.robot_pos[1]) ** 2
            )
            if dist > 2 * ROBOT_RADIUS:
                break
        self.opp_vel = [0.0, 0.0]
        self.step_count = 0
        return self._get_obs()

    def _get_obs(self):
        rp, rv, h = self.robot_pos, self.robot_vel, self.heading
        op, ov = self.opp_pos, self.opp_vel
        robot_dist = math.sqrt(rp[0] ** 2 + rp[1] ** 2)
        opp_rel_x = op[0] - rp[0]
        opp_rel_y = op[1] - rp[1]
        edge_dist = (RING_LIMIT - robot_dist) / RING_LIMIT
        fd = RING_LIMIT - math.sqrt(
            (rp[0] + 0.5 * math.cos(h)) ** 2 + (rp[1] + 0.5 * math.sin(h)) ** 2
        )
        edge_front = 1.0 - min(1.0, max(0.0, max(0, fd) / RING_LIMIT))
        bd = RING_LIMIT - math.sqrt(
            (rp[0] - 0.5 * math.cos(h)) ** 2 + (rp[1] - 0.5 * math.sin(h)) ** 2
        )
        edge_back = 1.0 - min(1.0, max(0.0, max(0, bd) / RING_LIMIT))
        la = h + math.pi / 2
        ld = RING_LIMIT - math.sqrt(
            (rp[0] + 0.5 * math.cos(la)) ** 2 + (rp[1] + 0.5 * math.sin(la)) ** 2
        )
        edge_left = 1.0 - min(1.0, max(0.0, max(0, ld) / RING_LIMIT))
        ra = h - math.pi / 2
        rd = RING_LIMIT - math.sqrt(
            (rp[0] + 0.5 * math.cos(ra)) ** 2 + (rp[1] + 0.5 * math.sin(ra)) ** 2
        )
        edge_right = 1.0 - min(1.0, max(0.0, max(0, rd) / RING_LIMIT))
        return np.array(
            [
                rp[0] / RING_LIMIT,
                rp[1] / RING_LIMIT,
                rv[0] / MAX_SPEED,
                rv[1] / MAX_SPEED,
                h / (2 * math.pi),
                self.angular_v / MAX_ANGULAR,
                opp_rel_x / RING_LIMIT,
                opp_rel_y / RING_LIMIT,
                ov[0] / MAX_SPEED,
                ov[1] / MAX_SPEED,
                edge_dist,
                edge_front,
                edge_back,
                edge_left,
                edge_right,
                self.step_count / 300.0,
            ],
            dtype=np.float32,
        )

    def step(self, action):
        linear, angular = ACTION_MAP.get(int(action), (0.0, 0.0))
        new_heading = (self.heading + angular * DT) % (2 * math.pi)
        wvx = math.cos(new_heading) * linear
        wvy = math.sin(new_heading) * linear
        self.robot_vel[0] = self.robot_vel[0] * FRICTION + wvx * (1 - FRICTION)
        self.robot_vel[1] = self.robot_vel[1] * FRICTION + wvy * (1 - FRICTION)
        self.robot_pos[0] += self.robot_vel[0] * DT
        self.robot_pos[1] += self.robot_vel[1] * DT
        self.heading = new_heading
        self.angular_v = angular
        self.opp_vel[0] *= FRICTION
        self.opp_vel[1] *= FRICTION
        self.opp_pos[0] += self.opp_vel[0] * DT
        self.opp_pos[1] += self.opp_vel[1] * DT
        dv = np.array([self.robot_pos[0] - self.opp_pos[0], self.robot_pos[1] - self.opp_pos[1]])
        d = np.linalg.norm(dv)
        min_d = 2 * ROBOT_RADIUS
        if d < min_d and d > 1e-6:
            overlap = min_d - d
            direction = dv / d
            self.robot_pos[0] += direction[0] * overlap * 0.5
            self.robot_pos[1] += direction[1] * overlap * 0.5
            self.opp_pos[0] -= direction[0] * overlap * 0.5
            self.opp_pos[1] -= direction[1] * overlap * 0.5
            rv_arr = np.array(
                [self.robot_vel[0] - self.opp_vel[0], self.robot_vel[1] - self.opp_vel[1]]
            )
            vn = rv_arr[0] * direction[0] + rv_arr[1] * direction[1]
            if vn < 0:
                self.robot_vel[0] -= vn * direction[0] * 0.5
                self.robot_vel[1] -= vn * direction[1] * 0.5
                self.opp_vel[0] += vn * direction[0] * 0.5
                self.opp_vel[1] += vn * direction[1] * 0.5
        self.step_count += 1
        robot_dist = math.sqrt(self.robot_pos[0] ** 2 + self.robot_pos[1] ** 2)
        opp_dist = math.sqrt(self.opp_pos[0] ** 2 + self.opp_pos[1] ** 2)
        done = False
        reward = 0.0
        if robot_dist >= RING_LIMIT:
            done = True
            reward = -10.0
        elif opp_dist >= RING_LIMIT:
            done = True
            reward = 50.0
        elif self.step_count >= 300:
            done = True
            reward = -5.0
        else:
            opp_dist_norm = opp_dist / RING_LIMIT
            edge_danger = (
                max(0, 1.0 - self._get_obs()[10] * 3) if robot_dist > RING_LIMIT * 0.6 else 1.0
            )
            reward = (1.0 - opp_dist_norm) * 0.1 - edge_danger * 0.2
        return self._get_obs(), reward, done


# ─── Student Model ───
class StudentMLP(nn.Module):
    def __init__(self, obs_dim=16, action_dim=11, hidden=None, dropout=0.1):
        if hidden is None:
            hidden = [128, 64]
        super().__init__()
        layers = []
        prev = obs_dim
        for _i, h in enumerate(hidden):
            layers.extend([nn.Linear(prev, h), nn.ReLU(), nn.Dropout(dropout)])
            prev = h
        layers.append(nn.Linear(prev, action_dim))
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x)


# ─── Data Collection ───
def collect_expert_data(n_episodes=500):
    """Collect expert demonstrations from V11."""
    data = []
    wins = 0
    total_steps = 0
    for ep in range(n_episodes):
        env = LightweightEnv(seed=ep + 1000)
        obs = env.reset()
        for step in range(300):  # noqa: B007
            action, qmax = v11_select_action(obs.tolist())
            data.append((obs.copy(), int(action), float(qmax)))
            obs, reward, done = env.step(action)
            if done:
                if reward > 0:
                    wins += 1
                break
        total_steps += step + 1
        if (ep + 1) % 100 == 0:
            print(
                f"  Expert ep {ep + 1:4d}: wins={wins}/{ep + 1} ({wins / (ep + 1):.1%}), steps={total_steps}"
            )
    print(f"Expert: {len(data)} pairs, {wins}/{n_episodes} wins ({wins / n_episodes:.1%})")
    return data


def collect_student_trajectories(student, n_episodes=100):
    """Run student policy, collect states (for DAgger relabeling)."""
    student.eval()
    states = []
    wins = 0
    for ep in range(n_episodes):
        env = LightweightEnv(seed=2000 + ep)
        obs = env.reset()
        ep_states = []
        while True:
            with torch.no_grad():
                out = student(torch.FloatTensor(obs))
                action = out.argmax().item()
            ep_states.append(obs.copy())
            obs, reward, done = env.step(action)
            if done:
                if reward > 0:
                    wins += 1
                    # Keep all states from winning episodes
                    states.extend(ep_states)
                elif len(ep_states) > 0:
                    # Keep partial from losing episodes too (critical for DAgger!)
                    states.extend(ep_states)
                break
    print(f"  Student trajectories: {len(states)} states from {n_episodes} episodes ({wins} wins)")
    return states, wins / n_episodes


def relabel_with_expert(states):
    """Get V11 expert labels for the given states."""
    data = []
    for obs in states:
        action, qmax = v11_select_action(obs.tolist())
        data.append((obs.copy(), int(action), float(qmax)))
    return data


# ─── Training ───
def train_student(all_data, hidden=None, epochs=200, batch_size=256, lr=3e-4, dropout=0.1):
    """Train student on aggregated dataset."""
    if hidden is None:
        hidden = [128, 64]
    states = torch.FloatTensor(np.array([d[0] for d in all_data]))
    expert_actions = torch.LongTensor([d[1] for d in all_data])
    expert_qmax = torch.FloatTensor([d[2] for d in all_data])

    student = StudentMLP(hidden=hidden, dropout=dropout)
    optimizer = optim.AdamW(student.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingWarmRestarts(optimizer, T_0=30, T_mult=2)

    n = len(states)
    print(f"Training {n} samples, hidden={hidden}, epochs={epochs}, dropout={dropout}...")
    best_acc = 0
    best_state = None

    for epoch in range(epochs):
        student.train()
        perm = torch.randperm(n)
        total_loss = 0
        correct = 0
        for i in range(0, n, batch_size):
            idx = perm[i : i + batch_size]
            s_batch = states[idx]
            a_batch = expert_actions[idx]
            q_batch = expert_qmax[idx]
            out = student(s_batch)
            loss = F.cross_entropy(out, a_batch, reduction="none")
            # qmax-weighted loss
            w = (q_batch - q_batch.min()) / (q_batch.max() - q_batch.min() + 1e-8)
            loss = (loss * w).mean()
            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(student.parameters(), 1.0)  # gradient clipping
            optimizer.step()
            total_loss += loss.item() * len(idx)
            correct += (out.argmax(1) == a_batch).sum().item()
        scheduler.step()
        acc = correct / n
        if acc > best_acc:
            best_acc = acc
            best_state = {k: v.clone() for k, v in student.state_dict().items()}
        if (epoch + 1) % 20 == 0:
            print(
                f"  Epoch {epoch + 1:3d}: loss={total_loss / n:.4f}, acc={acc:.2%} best={best_acc:.2%}"
            )
    student.load_state_dict(best_state)
    return student, best_acc


# ─── Evaluation ───
def evaluate_student(student, n_episodes=100):
    """Closed-loop evaluation."""
    student.eval()
    wins = 0
    action_counts = {}
    for ep in range(n_episodes):
        env = LightweightEnv(seed=5000 + ep)
        obs = env.reset()
        while True:
            with torch.no_grad():
                out = student(torch.FloatTensor(obs))
                action = out.argmax().item()
            action_counts[action] = action_counts.get(action, 0) + 1
            obs, reward, done = env.step(action)
            if done:
                if reward > 0:
                    wins += 1
                break
    return wins / n_episodes, action_counts


# ─── Export ───
def export_to_c(student, save_path, label="dagger"):
    weights = []
    biases = []
    for name, param in student.named_parameters():
        data = param.detach().cpu().numpy()
        if "weight" in name:
            out_dim, in_dim = data.shape
            weights.append((f"fc{len(weights) + 1}", data.reshape(-1).tolist(), out_dim, in_dim))
        elif "bias" in name:
            biases.append((f"fc{len(biases)}", data.tolist()))
    total = sum(len(w[1]) for w in weights) + sum(len(b[1]) for b in biases)

    hidden_dims = [w[2] for w in weights[:-1]]
    lines = [
        "// DQN Student Weights (DAgger from V11 Expert)",
        f"// {total} params (float32) | {label}",
        f"// Architecture: {OBS_DIM}→{'→'.join(str(d) for d in hidden_dims)}→{N_ACTIONS}",
        "",
        "// ====== Weights ======",
        "",
    ]
    for name, flat, _out_dim, _in_dim in weights:
        var_name = f"dqn_{name}_weight"
        lines.append(f"const float {var_name}[{len(flat)}] = {{")
        row = []
        for v in flat:
            row.append(f"{v:.8f}f")
            if len(row) >= 8:
                lines.append("    " + ", ".join(row) + ",")
                row = []
        if row:
            lines.append("    " + ", ".join(row))
        lines.append("};")
        lines.append("")

    lines.append("// ====== Biases ======")
    lines.append("")
    for name, bias in biases:
        var_name = f"dqn_{name}_bias"
        lines.append(f"const float {var_name}[{len(bias)}] = {{")
        lines.append("    " + ", ".join(f"{v:.8f}f" for v in bias))
        lines.append("};")
        lines.append("")

    with open(save_path, "w") as f:
        f.write("\n".join(lines))
    print(f"[Export] {total} params → {save_path}")


# ─── Main DAgger Pipeline ───
def main():
    print("=" * 60)
    print("DEBT-001 Fix v3: DAgger from V11 Expert")
    print("=" * 60)

    # ── Round 0: Collect expert data ──
    print("\n── Round 0: Expert Data Collection ──")
    expert_data = collect_expert_data(n_episodes=500)

    # ── Round 1: Initial BC training ──
    print("\n── Round 1: Initial Behavioral Cloning ──")
    all_data = list(expert_data)
    student, bc_acc = train_student(all_data, hidden=[128, 64], epochs=200, dropout=0.15)
    wr, ad = evaluate_student(student, n_episodes=100)
    print(f"Round 1 Eval: {wr:.1%} ({int(wr * 100)}/100) win rate")

    # ── DAgger Iterations ──
    dagger_iters = 3
    student_eps_per_iter = 150

    for dagger_iter in range(dagger_iters):
        print(f"\n── DAgger Iteration {dagger_iter + 1}/{dagger_iters} ──")

        # Collect student trajectories
        student_states, student_wr = collect_student_trajectories(
            student, n_episodes=student_eps_per_iter
        )

        # Relabel with expert
        new_data = relabel_with_expert(student_states)
        print(f"  Relabeled {len(new_data)} states with expert actions")

        # Aggregate
        all_data.extend(new_data)
        print(f"  Total dataset: {len(all_data)} samples")

        # Retrain
        student, bc_acc = train_student(all_data, hidden=[128, 64], epochs=150, dropout=0.15)

        # Evaluate
        wr, ad = evaluate_student(student, n_episodes=100)
        print(f"  DAgger {dagger_iter + 1} Eval: {wr:.1%} ({int(wr * 100)}/100) win rate")
        print(f"  Action dist: { {ACTION_NAMES.get(k, str(k)): v for k, v in sorted(ad.items())} }")

    # ── Final Evaluation ──
    print("\n── Final Evaluation (200 episodes) ──")
    final_wr, final_ad = evaluate_student(student, n_episodes=200)
    print(f"Final win rate: {final_wr:.1%} ({int(final_wr * 200)}/200)")
    print(
        f"Action distribution: { {ACTION_NAMES.get(k, str(k)): v for k, v in sorted(final_ad.items())} }"
    )

    # ── Export ──
    print("\n── Export ──")
    save_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dqn_weights_dagger.c")
    export_to_c(student, save_path, label=f"dagger_v3_wr{final_wr:.0%}")

    # ── Summary ──
    gate = "PASS" if final_wr >= 0.30 else "FAIL"
    print(f"\n{'=' * 60}")
    print("DEBT-001 DAgger Summary:")
    print("  V11 Expert win rate:  100%")
    print(f"  Final BC accuracy:    {bc_acc:.2%}")
    print(f"  Final closed-loop:    {final_wr:.1%}")
    print(f"  Gate (>30%):          {gate}")
    print(f"  Output:               {save_path}")
    print(f"{'=' * 60}")
    return final_wr


if __name__ == "__main__":
    main()
