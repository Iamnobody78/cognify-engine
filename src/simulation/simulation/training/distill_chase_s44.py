# -*- coding: utf-8 -*-
"""
S44 T1+T2: nano 泛化提升 — 蒸馏数据扩展 + 学生容量提升
============================================================================
PM 裁决 (S44): 路径 C 接受 92.5% 上界, 转向 nano 泛化。nano 差距 = random 6/8
vs 教师 7/8 (+1 局追平)。提升方向: (1) 蒸馏数据扩展 (345→1000+ 样本, 覆盖
random 多样化轨迹), (2) 学生容量提升 (16x2=789 → 24x2=1365 params, 教师 66%)。

方法: 行为克隆 (CE) — 学生 NanoQNet9(hidden_dim 可配) 拟合教师演示 (obs9->action21)。
collect_chase 13-slot 课程含 random 2/13, 扩 episodes → 更多 random 覆盖。

运行: python distill_chase_s44.py [--teacher <pt>] [--out <pt>] [--episodes 200]
                                  [--hidden-dim 24] [--n-hidden 2]
"""
import argparse
import os
import sys
import time

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
for p in (REPO_ROOT, os.path.join(REPO_ROOT, "bottlesumo_pi"),
          os.path.join(REPO_ROOT, "bottlesumo_pi", "simulation"),
          os.path.join(REPO_ROOT, "bottlesumo_pi", "rl")):
    if p not in sys.path:
        sys.path.insert(0, p)

from rl.chase_teacher_bc import CURRICULUM_POOL, collect_chase  # noqa: E402

N_ACTIONS = 21
STATE_DIM = 9
HP = {
    "n_epochs": 120,
    "batch_size": 128,
    "lr": 3e-4,
    "wd": 1e-4,
}


def collect_chase_net(n_episodes: int, q_net, seed: int = 42):
    """S45 T1b: 网络教师 rollout 版演示采集 (替代规则启发式).

    PM 指令 (S45): "用 DAgger 教师收集 500ep 轨迹" — 教师 = 已部署的
    chase_dqn_dagger_s40.pt (门禁 92.5%), 而非 S38 规则启发式。动作取
    q_net argmax (确定性, 与门评估一致), 课程同 collect_chase (13-slot,
    defensive scale=0.4 训练-评估一致性)。
    """
    import numpy as np

    from lightweight_env import LightweightBottleSumoEnv
    from v9_gate_evaluator import OpponentStrategies

    obs_hist, act_hist = [], []
    q_net.eval()
    with torch.no_grad():
        for ep in range(n_episodes):
            profile = CURRICULUM_POOL[ep % len(CURRICULUM_POOL)]
            if profile in ("random", "aggressive", "defensive", "circler", "counter"):
                env = LightweightBottleSumoEnv(
                    opponent_strategy=OpponentStrategies.get(profile),
                    opponent_speed_scale=(0.4 if profile == "defensive" else 1.0),
                    render_mode="none", seed=seed + ep,
                )
            else:
                env = LightweightBottleSumoEnv(
                    opponent_profile=profile,
                    render_mode="none", seed=seed + ep,
                )
            obs, _ = env.reset(seed=seed + ep)
            done = False
            steps = 0
            while not done and steps < 300:
                x = torch.FloatTensor(np.asarray(obs, dtype=np.float32)).unsqueeze(0)
                act = int(q_net(x).argmax(dim=1).item())
                obs_hist.append(np.asarray(obs, dtype=np.float32))
                act_hist.append(int(act))
                obs, _, done, truncated, _ = env.step(act)
                if truncated:
                    done = True
                steps += 1
    return np.array(obs_hist, dtype=np.float32), np.array(act_hist, dtype=np.int64)


class NanoQNet9(nn.Module):
    """9 维 obs 轻量学生网络 (hidden_dim 可配: 16x2=789, 24x2=1365, 32x2=2053)."""

    def __init__(self, state_dim=STATE_DIM, action_dim=N_ACTIONS,
                 hidden_dim=16, n_hidden=2):
        super().__init__()
        layers = [nn.Linear(state_dim, hidden_dim), nn.ReLU()]
        for _ in range(n_hidden - 1):
            layers += [nn.Linear(hidden_dim, hidden_dim), nn.ReLU()]
        layers.append(nn.Linear(hidden_dim, action_dim))
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", default="models/chase_dqn_dagger_s40.pt",
                    help="T1b: 网络教师权重 (--teacher-mode net 时使用, 默认 S40 DAgger)")
    ap.add_argument("--teacher-mode", choices=["rule", "net"], default="rule",
                    help="rule=S38 规则启发式 (S44 管线); net=网络 argmax rollout (S45 T1b)")
    ap.add_argument("--out", default="models/nano_s44.pt")
    ap.add_argument("--episodes", type=int, default=200, help="T1: 演示 episodes (60→200)")
    ap.add_argument("--hidden-dim", type=int, default=24, help="T2: 学生 hidden_dim (16→24)")
    ap.add_argument("--n-hidden", type=int, default=2)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    # 1) 采集教师演示 (13-slot 课程, random 2/13; 扩 episodes → 更多 random 覆盖)
    print(f"[S45] 采集演示 ({args.episodes} episodes, teacher_mode={args.teacher_mode})...")
    if args.teacher_mode == "net":
        from common.agent import DQNAgent
        from common.config import Config

        cfg = Config.quick_test()
        teacher = DQNAgent(cfg)
        teacher.q_net.load_state_dict(
            torch.load(args.teacher, map_location="cpu", weights_only=True)
        )
        obs, acts = collect_chase_net(args.episodes, teacher.q_net, seed=args.seed)
        print(f"[S45] 网络教师: {args.teacher}")
    else:
        obs, acts = collect_chase(args.episodes, seed=args.seed)
    obs = np.asarray(obs, dtype=np.float32)
    acts = np.asarray(acts, dtype=np.int64)
    n_random = int((acts >= 0).sum())  # placeholder; real per-profile split below
    print(f"[S45] 演示: {len(obs)} 样本, 动作分布 {np.bincount(acts, minlength=N_ACTIONS).tolist()}")

    # 2) 训练学生 (BC 交叉熵)
    torch.manual_seed(args.seed)
    model = NanoQNet9(hidden_dim=args.hidden_dim, n_hidden=args.n_hidden)
    opt = optim.Adam(model.parameters(), lr=HP["lr"], weight_decay=HP["wd"])
    n_params = sum(v.numel() for v in model.parameters())
    print(f"[S44] 学生 params: {n_params} (教师 2069 → {n_params/2069:.0%})")

    n = len(obs)
    idx = np.arange(n)
    best_acc = 0.0
    t0 = time.time()
    for ep in range(HP["n_epochs"]):
        np.random.shuffle(idx)
        total_loss, total_acc, nb = 0.0, 0.0, 0
        for i in range(0, n, HP["batch_size"]):
            b = idx[i:i + HP["batch_size"]]
            x = torch.FloatTensor(obs[b])
            y = torch.LongTensor(acts[b])
            opt.zero_grad()
            logits = model(x)
            loss = F.cross_entropy(logits, y)
            loss.backward()
            opt.step()
            total_loss += loss.item() * len(b)
            total_acc += (logits.argmax(dim=1) == y).sum().item()
            nb += len(b)
        acc = total_acc / nb
        if acc > best_acc:
            best_acc = acc
        if (ep + 1) % 20 == 0 or ep == 0:
            print(f"[S44] epoch {ep+1}/{HP['n_epochs']} loss={total_loss/nb:.4f} acc={acc:.1%}")
    print(f"[S44] 训练完成 {time.time()-t0:.1f}s, best_acc={best_acc:.1%}")

    torch.save(model.state_dict(), args.out)
    print(f"[S44] 已保存: {args.out} ({os.path.getsize(args.out)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
