#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sprint 36 T2: 规则层 -> RL 教师桥接 (行为克隆 warm-start).

用当前最优规则 Harness (ABDL 12 规则基线, V9 门教师) 在环境中 rollout,
收集 (obs, action) 数据集, 以交叉熵行为克隆预训练 DQN q_net,
输出 warm-start 权重供 DQN 训练 (train.py --init-weights) 使用。

用法:
  python3 rl/teacher_bc.py --episodes 60 --config quick_test --save models/abdl_teacher_bc.pt
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# REPO_ROOT = bottlesumo_pi 的父目录 (仓库根: aionrs-temp-48324704)
# 本文件在 bottlesumo_pi/rl/teacher_bc.py -> 三层 dirname 到仓库根
if os.path.basename(REPO_ROOT) != "aionrs-temp-48324704":
    # 兼容直接运行 (cwd = bottlesumo_pi)
    REPO_ROOT = os.path.dirname(os.path.abspath(__file__))  # bottlesumo_pi
for p in (REPO_ROOT,
          os.path.join(REPO_ROOT, "bottlesumo_pi"),
          os.path.join(REPO_ROOT, "bottlesumo_pi", "simulation")):
    if p not in sys.path:
        sys.path.insert(0, p)

from bottlesumo_pi.common import Config, DQNAgent
from lightweight_env import LightweightBottleSumoEnv

# ABDL 12 规则教师 (V9 门教师接口, 同 v9_gate_evaluator._lazy_init)
def _load_teacher():
    from core.meta_language.abdl_action_bridge import WorldStateBuilder, ABDLDecisionMaker
    rules_path = os.path.join(
        REPO_ROOT, "bottlesumo_pi", "governance",
        "meta_language", "simulation_rules.abdl",
    )
    if not os.path.isfile(rules_path):
        raise FileNotFoundError(f"ABDL rules not found: {rules_path}")
    wb = WorldStateBuilder()
    dm = ABDLDecisionMaker(rules_file=rules_path)
    return wb, dm


def collect_demonstrations(env, teacher, n_episodes: int, seed: int = 42):
    """ABDL 教师 rollout -> (obs_list, action_list)."""
    wb, dm = teacher
    obs_hist: list = []
    act_hist: list = []
    rng = random.Random(seed)
    for ep in range(n_episodes):
        obs, _ = env.reset(seed=seed + ep)
        done = False
        steps = 0
        while not done and steps < 300:
            world = wb.build(obs)
            action, _ = dm.decide_traced(world)
            if action is None:
                # 教师无匹配规则 -> 随机动作 (探索占位)
                action = rng.randrange(env.action_space.n)
            obs_hist.append(np.asarray(obs, dtype=np.float32))
            act_hist.append(int(action))
            obs, _, done, truncated, _ = env.step(action)
            if truncated:
                done = True
            steps += 1
    return np.array(obs_hist, dtype=np.float32), np.array(act_hist, dtype=np.int64)


def bc_train(q_net: nn.Module, obs: np.ndarray, acts: np.ndarray,
             epochs: int = 60, batch_size: int = 128, lr: float = 1e-3,
             device: str = "cpu") -> float:
    """行为克隆: softmax(Q) 交叉熵对齐教师动作. 返回最终 loss."""
    q_net.train()
    opt = optim.Adam(q_net.parameters(), lr=lr)
    criterion = nn.CrossEntropyLoss()
    n = len(obs)
    idx = np.arange(n)
    final_loss = 0.0
    for ep in range(epochs):
        rng = np.random.RandomState(42 + ep)
        rng.shuffle(idx)
        total = 0.0
        n_batches = 0
        for i in range(0, n, batch_size):
            b = idx[i:i + batch_size]
            ob = torch.FloatTensor(obs[b]).to(device)
            ac = torch.LongTensor(acts[b]).to(device)
            logits = q_net(ob)
            loss = criterion(logits, ac)
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += loss.item()
            n_batches += 1
        final_loss = total / max(n_batches, 1)
        if (ep + 1) % 20 == 0 or ep == epochs - 1:
            print(f"  BC epoch {ep + 1}/{epochs}: loss={final_loss:.4f}")
    return final_loss


def main():
    ap = argparse.ArgumentParser(description="ABDL 教师行为克隆 (S36 T2)")
    ap.add_argument("--episodes", type=int, default=60, help="教师 rollout episode 数")
    ap.add_argument("--config", default="quick_test",
                    choices=["default", "quick_test", "nano", "bayesopt_dqn"],
                    help="DQN 网络架构配置")
    ap.add_argument("--save", default=None, help="warm-start 权重保存路径")
    ap.add_argument("--epochs", type=int, default=60, help="BC 训练 epoch 数")
    args = ap.parse_args()

    cfg_map = {
        "default": Config(),
        "quick_test": Config.quick_test(),
        "nano": Config.nano(),
        "bayesopt_dqn": Config.bayesopt_dqn(),
    }
    cfg = cfg_map[args.config]
    save_path = args.save or os.path.join(
        REPO_ROOT, "bottlesumo_pi", "models",
        f"abdl_teacher_bc_{args.config}.pt",
    )
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    print("═" * 62)
    print("S36 T2: ABDL 12-rule teacher -> DQN behavior cloning (warm-start)")
    print(f"  config={args.config} | architecture={cfg.state_dim}→{cfg.hidden_dim}→{cfg.action_dim}")
    print("═" * 62)

    teacher = _load_teacher()
    print(f"  Teacher loaded: ABDL 12-rule baseline (simulation_rules.abdl)")

    env = LightweightBottleSumoEnv(
        opponent_profile=cfg.opponent_profile,
        render_mode="none",
        seed=42,
        edge_penalty_weight=cfg.edge_penalty_weight,
        push_threshold=cfg.push_threshold,
    )
    t0 = time.time()
    obs, acts = collect_demonstrations(env, teacher, args.episodes)
    print(f"  Demonstrations: {len(obs)} (obs, action) pairs in {time.time() - t0:.1f}s")
    print(f"  Action coverage: {np.unique(acts).size}/{cfg.action_dim} discrete actions")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    agent = DQNAgent(cfg)
    loss = bc_train(agent.q_net, obs, acts, epochs=args.epochs, device=device)
    agent.q_net.eval()

    # 评估 BC 对齐率 (教师动作命中率)
    with torch.no_grad():
        logits = agent.q_net(torch.FloatTensor(obs).to(device))
        pred = logits.argmax(dim=1).cpu().numpy()
        acc = (pred == acts).mean()
    print(f"  BC final loss={loss:.4f} | teacher-action accuracy={acc:.1%}")

    torch.save(agent.q_net.state_dict(), save_path)
    print(f"  Saved warm-start weights: {save_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
