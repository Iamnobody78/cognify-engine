#!/usr/bin/env python3
"""
DEBT-001 Fix v3: DAgger — Fast Iteration Version
Reduced scale: 300 expert eps, 100 BC epochs, 2 DAgger iters (80eps, 80 epochs), 100 eval
"""

import math
import os
import random
import sys
import time

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
            if (
                math.hypot(self.opp_pos[0] - self.robot_pos[0], self.opp_pos[1] - self.robot_pos[1])
                > 2 * ROBOT_RADIUS
            ):
                break
        self.opp_vel = [0.0, 0.0]
        self.step_count = 0
        return self._get_obs()

    def _get_obs(self):
        rp, rv, h = self.robot_pos, self.robot_vel, self.heading
        op, ov = self.opp_pos, self.opp_vel
        robot_dist = math.hypot(rp[0], rp[1])
        opp_rel_x = op[0] - rp[0]
        opp_rel_y = op[1] - rp[1]
        edge_dist = (RING_LIMIT - robot_dist) / RING_LIMIT
        fd = RING_LIMIT - math.hypot(rp[0] + 0.5 * math.cos(h), rp[1] + 0.5 * math.sin(h))
        edge_front = 1.0 - min(1.0, max(0.0, max(0, fd) / RING_LIMIT))
        bd = RING_LIMIT - math.hypot(rp[0] - 0.5 * math.cos(h), rp[1] - 0.5 * math.sin(h))
        edge_back = 1.0 - min(1.0, max(0.0, max(0, bd) / RING_LIMIT))
        la = h + math.pi / 2
        ld = RING_LIMIT - math.hypot(rp[0] + 0.5 * math.cos(la), rp[1] + 0.5 * math.sin(la))
        edge_left = 1.0 - min(1.0, max(0.0, max(0, ld) / RING_LIMIT))
        ra = h - math.pi / 2
        rd = RING_LIMIT - math.hypot(rp[0] + 0.5 * math.cos(ra), rp[1] + 0.5 * math.sin(ra))
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
        if d < 2 * ROBOT_RADIUS and d > 1e-6:
            overlap = 2 * ROBOT_RADIUS - d
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
        robot_dist = math.hypot(self.robot_pos[0], self.robot_pos[1])
        opp_dist = math.hypot(self.opp_pos[0], self.opp_pos[1])
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
        return self._get_obs(), reward, done


class StudentMLP(nn.Module):
    def __init__(self, hidden=None, dropout=0.1):
        if hidden is None:
            hidden = [128, 64]
        super().__init__()
        layers = [
            nn.Linear(16, hidden[0]),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden[0], hidden[1]),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden[1], 11),
        ]
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x)


def collect_expert(n_episodes=300):
    data = []
    wins = 0
    for ep in range(n_episodes):
        env = LightweightEnv(seed=ep + 1000)
        obs = env.reset()
        for _step in range(300):
            action, qmax = v11_select_action(obs.tolist())
            data.append((obs.copy(), int(action), float(qmax)))
            obs, reward, done = env.step(action)
            if done:
                if reward > 0:
                    wins += 1
                break
        if (ep + 1) % 100 == 0:
            print(f"  Expert {ep + 1}: {wins} wins")
    print(f"Expert: {len(data)} pairs, {wins}/{n_episodes} wins")
    return data


def collect_student_states(student, n_episodes=80):
    student.eval()
    states = []
    wins = 0
    for ep in range(n_episodes):
        env = LightweightEnv(seed=2000 + ep)
        obs = env.reset()
        ep_states = []
        while True:
            with torch.no_grad():
                action = student(torch.FloatTensor(obs)).argmax().item()
            ep_states.append(obs.copy())
            obs, reward, done = env.step(action)
            if done:
                if reward > 0:
                    wins += 1
                states.extend(ep_states)
                break
    return states, wins / n_episodes


def train(all_data, epochs=100, lr=3e-4):
    states = torch.FloatTensor(np.array([d[0] for d in all_data]))
    actions = torch.LongTensor([d[1] for d in all_data])
    qmax = torch.FloatTensor([d[2] for d in all_data])
    student = StudentMLP()
    opt = optim.AdamW(student.parameters(), lr=lr, weight_decay=1e-4)
    sch = optim.lr_scheduler.CosineAnnealingWarmRestarts(opt, T_0=20, T_mult=2)
    n = len(states)
    best_acc = 0
    best_state = None
    for epoch in range(epochs):
        student.train()
        perm = torch.randperm(n)
        correct = 0
        for i in range(0, n, 256):
            idx = perm[i : i + 256]
            s, a, q = states[idx], actions[idx], qmax[idx]
            out = student(s)
            loss = F.cross_entropy(out, a, reduction="none")
            w = (q - q.min()) / (q.max() - q.min() + 1e-8)
            loss = (loss * w).mean()
            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(student.parameters(), 1.0)
            opt.step()
            correct += (out.argmax(1) == a).sum().item()
        sch.step()
        acc = correct / n
        if acc > best_acc:
            best_acc = acc
            best_state = {k: v.clone() for k, v in student.state_dict().items()}
        if (epoch + 1) % 20 == 0:
            print(f"    Epoch {epoch + 1:3d}: acc={acc:.2%} best={best_acc:.2%}")
    student.load_state_dict(best_state)
    return student, best_acc


def evaluate(student, n_episodes=100):
    student.eval()
    wins = 0
    ad = {}
    for ep in range(n_episodes):
        env = LightweightEnv(seed=5000 + ep)
        obs = env.reset()
        while True:
            with torch.no_grad():
                a = student(torch.FloatTensor(obs)).argmax().item()
            ad[a] = ad.get(a, 0) + 1
            obs, reward, done = env.step(a)
            if done:
                if reward > 0:
                    wins += 1
                break
    return wins / n_episodes, ad


def export_c(student, path):
    weights = []
    biases = []
    for name, param in student.named_parameters():
        data = param.detach().cpu().numpy()
        if "weight" in name:
            out_dim, in_dim = data.shape
            weights.append((f"fc{len(weights) + 1}", data.reshape(-1).tolist(), out_dim, in_dim))
        else:
            biases.append((f"fc{len(biases)}", data.tolist()))
    total = sum(len(w[1]) for w in weights)
    lines = [
        "// DQN Student (DAgger from V11 Expert)",
        f"// {total} float32 params",
        "// Architecture: 16→128→64→11",
        "",
        "// ====== Weights ======",
        "",
    ]
    for name, flat, _out_dim, _in_dim in weights:
        lines.append(f"const float dqn_{name}_weight[{len(flat)}] = {{")
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
        lines.append(f"const float dqn_{name}_bias[{len(bias)}] = {{")
        lines.append("    " + ", ".join(f"{v:.8f}f" for v in bias))
        lines.append("};")
        lines.append("")
    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"Exported {total} params → {path}")


def main():
    print("=" * 60)
    print("DEBT-001 v3: DAgger Fast Iteration")
    print("=" * 60)
    t0 = time.time()

    # Round 0: Expert
    print("\n── Round 0: Expert Data ──")
    all_data = list(collect_expert(300))

    # Round 1: BC
    print("\n── Round 1: Initial BC ──")
    student, bc_acc = train(all_data, epochs=100)
    wr, ad = evaluate(student, 50)
    print(f"  BC Eval (50ep): {wr:.0%} win, acc={bc_acc:.2%}")

    # DAgger iterations
    for di in range(2):
        print(f"\n── DAgger Iter {di + 1}/2 ──")
        ss, swr = collect_student_states(student, 80)
        nd = [
            (
                s.copy(),
                int(v11_select_action(s.tolist())[0]),
                float(v11_select_action(s.tolist())[1]),
            )
            for s in ss
        ]
        print(f"  +{len(nd)} relabeled states (student WR={swr:.0%})")
        all_data.extend(nd)
        student, bc_acc = train(all_data, epochs=80, lr=2e-4)
        wr, ad = evaluate(student, 50)
        print(f"  Eval (50ep): {wr:.0%} win")

    # Final
    print("\n── Final (100ep) ──")
    wr, ad = evaluate(student, 100)
    print(f"FINAL: {wr:.0%} ({int(wr * 100)}/100)")
    dist = {ACTION_NAMES.get(k, str(k)): v for k, v in sorted(ad.items())}
    print(f"Actions: {dist}")

    sp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dqn_weights_dagger.c")
    export_c(student, sp)

    elapsed = time.time() - t0
    gate = "PASS" if wr >= 0.30 else "FAIL"
    print(f"\n{'=' * 60}")
    print(f"Summary: WR={wr:.0%} | Gate={gate} | Time={elapsed:.0f}s | {sp}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
