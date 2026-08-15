# -*- coding: utf-8 -*-
"""
S39 T1: DQN fine-tune fix (FP-RL-005) — skill-protection 微调
================================================================
FP-RL-005 机制: BC 权重门 90%, 但任意 DQN fine-tune → 恒定 40%.
  追求 = 数十步时间一致行为; 混合回放 + epsilon-greedy 打断成功轨迹
  → 收敛到 "对头" 妥协。

PM 技术路径 (S39 裁决): 低 epsilon + skill-protection 正则
  - epsilon 0.1 → 0.01-0.05 (低探索, 保持 BC 时间一致性)
  - 冻结 BC-warmed 早期层 (fc1 = net[0])
  - L2 正则: loss += skill_lambda * Σ(p - p_bc)² (trainable params)

验收: 微调门 ≥ 90.0% (36/40), 双端回归绿。

运行: python finetune_dqn_s39.py [--episodes 1000] [--skill-lambda 1e-3]
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
          os.path.join(REPO_ROOT, "bottlesumo_pi", "simulation")):
    if p not in sys.path:
        sys.path.insert(0, p)

from bottlesumo_pi.common.config import Config  # noqa: E402
from bottlesumo_pi.common.agent import DQNAgent  # noqa: E402
from bottlesumo_pi.common import evaluate  # noqa: E402
from bottlesumo_pi.simulation.lightweight_env import LightweightBottleSumoEnv  # noqa: E402
from bottlesumo_pi.simulation.training.train import (  # noqa: E402
    CURRICULUM_POOL, GATE_BEHAVIORS, train_episode,
)

BC_WEIGHTS = os.path.join(REPO_ROOT, "bottlesumo_pi", "models", "chase_teacher_bc_s38_v2.pt")
DEFAULT_OUT = os.path.join(REPO_ROOT, "bottlesumo_pi", "models", "chase_dqn_finetune_s39.pt")


class SkillProtectedAgent(DQNAgent):
    """FP-RL-005 修复: 低 epsilon + skill-protection 微调。

    - 从 BC-warmed 权重初始化 q_net + target_net
    - 冻结早期层 (fc1 = net[0]) — 保持 BC 追求表征
    - L2 正则拉向 BC 权重: loss += skill_lambda * Σ(p - p_bc)² (trainable)
    - 低 epsilon (cfg.epsilon_start=0.05 → epsilon_end=0.01)
    """

    def __init__(self, cfg, bc_state_dict, freeze_prefixes=("net.0.",), skill_lambda=1e-3):
        super().__init__(cfg)
        # BC-warmed init
        self.q_net.load_state_dict(bc_state_dict)
        self.target_net.load_state_dict(bc_state_dict)
        # 冻结早期层
        self.frozen_names = set()
        for name, p in self.q_net.named_parameters():
            if name.startswith(freeze_prefixes):
                p.requires_grad = False
                self.frozen_names.add(name)
        # L2 参考快照 (仅 trainable)
        self.bc_ref = {
            name: p.detach().clone()
            for name, p in self.q_net.named_parameters()
            if p.requires_grad
        }
        self.skill_lambda = skill_lambda
        # 重建 optimizer (仅 trainable)
        self.optimizer = optim.Adam(
            [p for name, p in self.q_net.named_parameters() if p.requires_grad],
            lr=cfg.learning_rate,
        )
        self.epsilon = cfg.epsilon_start
        print(f"  冻结层: {sorted(self.frozen_names) or '(无)'} | skill_lambda={skill_lambda}")

    def update(self) -> float:
        """DQN update + skill-protection L2 正则."""
        if len(self.replay_buffer) < self.cfg.batch_size:
            return 0.0
        s, a, r, ns, d = self.replay_buffer.sample(self.cfg.batch_size)
        s, a, r, ns, d = (s.to(self.device), a.to(self.device), r.to(self.device),
                          ns.to(self.device), d.to(self.device))
        q_values = self.q_net(s).gather(1, a.unsqueeze(1)).squeeze(1)
        with torch.no_grad():
            if self.cfg.use_double_dqn:
                best_actions = self.q_net(ns).argmax(dim=1)
                target_next = self.target_net(ns).gather(1, best_actions.unsqueeze(1)).squeeze(1)
            else:
                target_next = self.target_net(ns).max(dim=1).values
            target = r + self.cfg.gamma * target_next * (1 - d)
        loss = F.smooth_l1_loss(q_values, target)
        # skill-protection L2: 拉向 BC 权重
        if self.skill_lambda > 0:
            l2 = torch.zeros((), device=self.device)
            for name, p in self.q_net.named_parameters():
                if name in self.bc_ref:
                    l2 = l2 + ((p - self.bc_ref[name]) ** 2).sum()
            loss = loss + self.skill_lambda * l2
        self.optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self.q_net.parameters(), self.cfg.clip_grad_norm)
        self.optimizer.step()
        # epsilon decay (linear)
        self.total_steps += 1
        if self.cfg.epsilon_decay > 0:
            frac = min(self.total_steps / self.cfg.epsilon_decay, 1.0)
            self.epsilon = self.cfg.epsilon_start + frac * (self.cfg.epsilon_end - self.cfg.epsilon_start)
        # target sync
        if self.total_steps % self.cfg.target_update_freq == 0:
            self.target_net.load_state_dict(self.q_net.state_dict())
        return loss.item()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=1000)
    ap.add_argument("--skill-lambda", type=float, default=1e-3)
    ap.add_argument("--init-weights", default=BC_WEIGHTS)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    if not os.path.isfile(args.init_weights):
        raise FileNotFoundError(f"BC weights not found: {args.init_weights}")

    # Config: quick_test 架构 (32x1 = 2069 params, 与门评估一致) + 低 epsilon
    cfg = Config.quick_test()
    cfg.n_episodes = args.episodes
    cfg.epsilon_start = 0.05   # PM: 0.1→0.01-0.05
    cfg.epsilon_end = 0.01
    cfg.epsilon_decay = 2000   # 每 episode ~40-60 步; 2000 步后稳定在 0.01
    cfg.buffer_size = 20000
    cfg.batch_size = 64
    cfg.learning_rate = 3e-4
    cfg.target_update_freq = 100
    cfg.eval_freq = 50
    cfg.eval_episodes = 30
    cfg.save_name = os.path.basename(args.out)
    cfg.save_dir = os.path.dirname(args.out)

    print(f"╔{'═' * 60}╗")
    print(f"║  S39 T1: DQN fine-tune (FP-RL-005 fix)   ║")
    print(f"╚{'═' * 60}╝")
    print(f"  BC init: {args.init_weights}")
    print(f"  episodes={cfg.n_episodes} eps={cfg.epsilon_start}→{cfg.epsilon_end} "
          f"decay={cfg.epsilon_decay} lr={cfg.learning_rate}")
    print(f"  buffer={cfg.buffer_size} batch={cfg.batch_size} target_sync={cfg.target_update_freq}")
    print(f"  out: {args.out}")

    # Agent (skill-protected, BC-warmed)
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    bc_sd = torch.load(args.init_weights, map_location="cpu", weights_only=True)
    agent = SkillProtectedAgent(cfg, bc_sd, skill_lambda=args.skill_lambda)

    eval_env = LightweightBottleSumoEnv(
        opponent_profile=cfg.opponent_profile,
        render_mode="none",
        seed=cfg.n_episodes + 9999,
        edge_penalty_weight=cfg.edge_penalty_weight,
        push_threshold=cfg.push_threshold,
    )
    train_env = LightweightBottleSumoEnv(
        opponent_profile=cfg.opponent_profile,
        render_mode="none",
        seed=42,
        edge_penalty_weight=cfg.edge_penalty_weight,
        push_threshold=cfg.push_threshold,
    )

    history = {"episode": [], "reward": [], "win_rate": [], "epsilon": [], "loss": []}
    best_wr = 0.0
    t_start = time.time()
    for ep in range(cfg.n_episodes):
        # 与 train.py 一致: 13-slot 课程池 + defensive scale 0.40 (训练-评估一致)
        profile = CURRICULUM_POOL[ep % len(CURRICULUM_POOL)]
        train_env.close()
        if profile in GATE_BEHAVIORS:
            train_env = LightweightBottleSumoEnv(
                opponent_strategy=GATE_BEHAVIORS[profile],
                opponent_speed_scale=(0.40 if profile == "defensive" else 1.0),
                render_mode="none",
                seed=42 + ep,
                edge_penalty_weight=cfg.edge_penalty_weight,
                push_threshold=cfg.push_threshold,
            )
        else:
            train_env = LightweightBottleSumoEnv(
                opponent_profile=profile,
                render_mode="none",
                seed=42 + ep,
                edge_penalty_weight=cfg.edge_penalty_weight,
                push_threshold=cfg.push_threshold,
            )
        ep_reward, steps = train_episode(agent, train_env, ep, cfg)
        history["episode"].append(ep)
        history["reward"].append(ep_reward)

        if (ep + 1) % cfg.eval_freq == 0 or ep == 0 or ep == cfg.n_episodes - 1:
            result = evaluate(
                agent.q_net, eval_env,
                n_episodes=cfg.eval_episodes,
                win_threshold=cfg.win_threshold,
                edge_threshold=cfg.edge_threshold,
                verbose=False,
            )
            wr = result["win_rate_pct"]
            history["win_rate"].append(wr)
            history["epsilon"].append(agent.epsilon)
            improved = "↑" if wr > best_wr else " "
            if wr > best_wr:
                best_wr = wr
                agent.save(cfg.save_path + ".best")
            print(f"  Ep {ep + 1:4d}/{cfg.n_episodes} | WR={wr:5.1f}% {improved} "
                  f"| eps={agent.epsilon:.3f} | {time.time()-t_start:.0f}s")
    train_env.close()

    final_result = evaluate(
        agent.q_net, eval_env,
        n_episodes=cfg.eval_episodes * 3,
        win_threshold=cfg.win_threshold,
        edge_threshold=cfg.edge_threshold,
    )
    print(f"\n{'─' * 60}")
    print(f"  最终评估: WR={final_result['win_rate_pct']:.1f}% "
          f"drops={final_result['edge_drops']} R={final_result['avg_reward']:.1f}")
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    agent.save(args.out)
    print(f"  已保存: {args.out} ({os.path.getsize(args.out)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
