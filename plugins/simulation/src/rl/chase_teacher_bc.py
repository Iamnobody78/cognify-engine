#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sprint 37: 全知追敌教师 -> 行为克隆 (第二代教师桥).

背景 (FP-RL-003 判定链):
  1. 9 维观测信息充分 — obs[5]=opp_angle_rel 即"指向对手的角差", 与全知追敌
     启发式所用信息等价 (追敌基线: random 10/10, circler 9/10, defensive 0/10)
  2. 但 9 维 DQN 在混合对手上 1000ep/5000ep 门结果不变 (random/circler 0/4)
     -> 不是表征问题, 是 RL 训练动态: "追击"是数十步时序一致行为, epsilon
     噪声打断回放中的成功轨迹, 单帧折中策略在混合对手上退化为"对冲型"
  3. 解法: 全知追敌启发式 (仅离线采集用, 部署时学生只见 9 维观测) BC 预热,
     将追击技能直接注入 q_net, 再由 DQN 微调 (train.py --init-weights)

用法:
  python3 rl/chase_teacher_bc.py --episodes 60 --config quick_test \
      --save models/chase_teacher_bc_s37.pt
"""

from __future__ import annotations

import argparse
import math
import os
import sys

import numpy as np
import torch

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.path.basename(REPO_ROOT) != "aionrs-temp-48324704":
    REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
for p in (REPO_ROOT,
          os.path.join(REPO_ROOT, "bottlesumo_pi"),
          os.path.join(REPO_ROOT, "bottlesumo_pi", "simulation")):
    if p not in sys.path:
        sys.path.insert(0, p)

from bottlesumo_pi.common import Config, DQNAgent
from lightweight_env import LightweightBottleSumoEnv
from v9_gate_evaluator import OpponentStrategies
from wheel_to_discrete import Action
from teacher_bc import bc_train

# 13-slot weighted curriculum (同 train.py CURRICULUM_POOL): gate 行为 ×2 + 速度阶梯 ×1
CURRICULUM_POOL = [
    "random", "aggressive", "defensive", "circler", "counter",
    "random", "aggressive", "defensive", "circler", "counter",
    "moderate", "passive", "stationary",
]


def normalize(a: float) -> float:
    while a > math.pi:
        a -= 2 * math.pi
    while a < -math.pi:
        a += 2 * math.pi
    return a


def chase_action(env) -> int:
    """全知追敌启发式: 直接朝对手 (内部状态) 最大转向 + 满速, 边缘安全回避.
    仅用于离线演示采集 (教师可见内部状态; 学生部署时不可见).

    S38 T2 修正: 追击档位 MED(0.15)→FAST(0.30) — 审计发现 defensive (scale=0.4)
    直线移动 0.212, 旧 MED/低速转向追击有效速度仅 0.23 < 0.265 (scale=0.5 时代)
    → 越追越远 (dist 0.34→0.44 发散) 最终机器人逛到边缘落台。0.30 > 0.212
    才能建立追击并完成边缘推挤 (门协议实测: scale 0.4 → defensive 6/8)。
    边缘纪律 0.10→0.15: 追丢后避免逛到边缘 (FP-RL-006 修复后的新防线)。
    """
    dx = env.opponent_x - env.robot_x
    dy = env.opponent_y - env.robot_y
    desired = math.atan2(dy, dx)
    diff = normalize(desired - env.robot_theta)
    obs = env._get_obs()
    edge_min = min(obs[0], obs[1], obs[2], obs[3])
    if edge_min < 0.15:
        c_des = math.atan2(-env.robot_y, -env.robot_x)
        c_diff = normalize(c_des - env.robot_theta)
        if c_diff > 0.35:
            return int(Action.FW_LEFT_HARD)
        if c_diff < -0.35:
            return int(Action.FW_RIGHT_HARD)
        if c_diff > 0.1:
            return int(Action.FW_LEFT_FAST)
        if c_diff < -0.1:
            return int(Action.FW_RIGHT_FAST)
        return int(Action.FW_MAX)
    ad = abs(diff)
    if ad > 0.55:
        return int(Action.FW_LEFT_HARD) if diff > 0 else int(Action.FW_RIGHT_HARD)
    if ad > 0.22:
        return int(Action.FW_LEFT_FAST) if diff > 0 else int(Action.FW_RIGHT_FAST)
    if ad > 0.08:
        return int(Action.FW_LEFT_FAST) if diff > 0 else int(Action.FW_RIGHT_FAST)
    return int(Action.FW_MAX)


def collect_chase(n_episodes: int, seed: int = 42):
    obs_hist, act_hist = [], []
    for ep in range(n_episodes):
        profile = CURRICULUM_POOL[ep % len(CURRICULUM_POOL)]
        if profile in ("random", "aggressive", "defensive", "circler", "counter"):
            env = LightweightBottleSumoEnv(
                opponent_strategy=OpponentStrategies.get(profile),
                # S38 T2: defensive 训练-评估一致性 (门用 scale=0.4, 实测 6/8)
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
            act = chase_action(env)
            obs_hist.append(np.asarray(obs, dtype=np.float32))
            act_hist.append(int(act))
            obs, _, done, truncated, _ = env.step(act)
            if truncated:
                done = True
            steps += 1
    return np.array(obs_hist, dtype=np.float32), np.array(act_hist, dtype=np.int64)


def main():
    ap = argparse.ArgumentParser(description="全知追敌教师行为克隆 (S37 第二代教师桥)")
    ap.add_argument("--episodes", type=int, default=60)
    ap.add_argument("--config", default="quick_test",
                    choices=["default", "quick_test", "nano", "bayesopt_dqn"])
    ap.add_argument("--save", default=None)
    ap.add_argument("--epochs", type=int, default=60)
    args = ap.parse_args()

    cfg = {
        "default": Config(),
        "quick_test": Config.quick_test(),
        "nano": Config.nano(),
        "bayesopt_dqn": Config.bayesopt_dqn(),
    }.get(args.config, Config())
    agent = DQNAgent(cfg)
    print(f"[chase-BC] 采集全知追敌演示: {args.episodes}ep, obs_dim={cfg.state_dim}")

    obs, acts = collect_chase(args.episodes)
    print(f"[chase-BC] 演示: {len(obs)} 条 (obs{obs.shape[1]}d)")

    loss = bc_train(agent.q_net, obs, acts, epochs=args.epochs)
    with torch.no_grad():
        logits = agent.q_net(torch.FloatTensor(obs))
        pred = logits.argmax(dim=1).numpy()
        acc = float((pred == acts).mean())
    print(f"[chase-BC] 最终 loss={loss:.4f}, 教师动作复现率={acc:.1%}")

    if args.save:
        os.makedirs(os.path.dirname(args.save), exist_ok=True)
        torch.save(agent.q_net.state_dict(), args.save)
        print(f"[chase-BC] warm-start 权重 -> {args.save}")


if __name__ == "__main__":
    main()
