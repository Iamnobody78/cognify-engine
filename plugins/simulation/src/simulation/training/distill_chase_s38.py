# -*- coding: utf-8 -*-
"""
S38 T3: V9 plateau self-distillation — chase-BC 教师 → 轻量学生 (9 维 obs)
============================================================================
PM 裁决 (S38): V9 plateau 自蒸馏条件已满足 (门 ≥60%), 用 chase-BC 演示作为
教师数据, 跑 distill loop → 轻量策略。

验收: 蒸馏门 ≥60%, 模型尺寸 ≤50% 教师 (教师 2069 params → 学生 789 params, 38%).

方法: 行为克隆 — 学生 NanoQNet(16x2) 拟合演示 (obs9 -> action21) 的交叉熵。
     (chase 教师 = omniscient 追击, 演示数据含 FAST 追击 + defensive scale 0.4
      训练-评估一致, 学生继承该策略。)

运行: python distill_chase_s38.py [--teacher <pt>] [--out <pt>] [--episodes 60]
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

from rl.chase_teacher_bc import collect_chase  # noqa: E402

N_ACTIONS = 21
STATE_DIM = 9
HP = {
    "n_epochs": 120,
    "batch_size": 128,
    "lr": 3e-4,
    "hidden_dim": 16,
    "n_hidden": 2,
    "wd": 1e-4,
}


class NanoQNet9(nn.Module):
    """9 维 obs 轻量学生网络 (16x2 = 789 params, 教师 38%)."""

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


def _load_teacher_qnet(path: str) -> nn.Module:
    """S39 T2: 加载教师 q_net (chase-BC teacher, quick_test 32x1 = 2069 params)."""
    from common.config import Config  # noqa: E402
    from common.agent import DQNAgent  # noqa: E402
    cfg = Config.quick_test()
    agent = DQNAgent(cfg)
    agent.q_net.load_state_dict(
        torch.load(path, map_location="cpu", weights_only=True)
    )
    agent.q_net.eval()
    return agent.q_net


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", default="models/chase_teacher_bc_s38_v2.pt")
    ap.add_argument("--out", default="models/nano_s38.pt")
    ap.add_argument("--episodes", type=int, default=60)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--temp", type=float, default=0.0,
        help="S39 T2: 蒸馏温度 (>0 = 软目标 KL, 0 = 硬标签 CE)",
    )
    args = ap.parse_args()

    # 1) 采集 chase 教师演示 (训练-评估一致: defensive scale 0.4 已在 collect_chase 内)
    print(f"[T3] 采集演示 ({args.episodes} episodes)...")
    obs, acts = collect_chase(args.episodes, seed=args.seed)
    obs = np.asarray(obs, dtype=np.float32)
    acts = np.asarray(acts, dtype=np.int64)
    print(f"[T3] 演示: {len(obs)} 样本, 动作分布 {np.bincount(acts, minlength=N_ACTIONS).tolist()}")

    # S39 T2: 温度蒸馏 — 软目标来自教师 logits (Hinton distillation)
    teacher_q = None
    teacher_logits_all = None
    if args.temp > 0:
        teacher_q = _load_teacher_qnet(args.teacher)
        print(f"[T3] 教师 q_net 加载: {args.teacher} (temp={args.temp})")
        with torch.no_grad():
            t_logits = []
            for i in range(0, len(obs), 1024):
                xb = torch.FloatTensor(obs[i:i + 1024])
                t_logits.append(teacher_q(xb).detach())
            teacher_logits_all = torch.cat(t_logits, dim=0)  # (n, 21)

    # 2) 训练学生 (BC 交叉熵 / 温度软目标 KL)
    torch.manual_seed(args.seed)
    model = NanoQNet9(hidden_dim=HP["hidden_dim"], n_hidden=HP["n_hidden"])
    opt = optim.Adam(model.parameters(), lr=HP["lr"], weight_decay=HP["wd"])
    n_params = sum(v.numel() for v in model.parameters())
    print(f"[T3] 学生 params: {n_params} (教师 2069 → {n_params/2069:.0%})")

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
            if args.temp > 0:
                with torch.no_grad():
                    p = F.softmax(teacher_logits_all[b] / args.temp, dim=1)
                log_q = F.log_softmax(logits / args.temp, dim=1)
                loss = F.kl_div(log_q, p, reduction="batchmean") * args.temp * args.temp
            else:
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
            print(f"[T3] epoch {ep+1}/{HP['n_epochs']} loss={total_loss/nb:.4f} acc={acc:.1%}")
    print(f"[T3] 训练完成 {time.time()-t0:.1f}s, best_acc={best_acc:.1%}")

    torch.save(model.state_dict(), args.out)
    print(f"[T3] 已保存: {args.out} ({os.path.getsize(args.out)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
