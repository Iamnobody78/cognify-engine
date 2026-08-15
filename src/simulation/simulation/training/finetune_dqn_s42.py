"""
finetune_dqn_s40.py — Sprint 40 T1: DAgger online-correction fine-tune prototype.

FP-RL-005 root cause (S39): mixed replay + epsilon-greedy interrupts tens-of-steps
temporally-consistent pursuit trajectories → Q collapses to single action (FW_MAX).
S39 SkillProtected (freeze fc1 + L2 + low-eps) only mitigated 40% → 60%.

S40 DAgger mechanism (per PM spec):
  - beta annealing 1.0 → 0.1 over training steps: early = full teacher override,
    late = mostly autonomous.  Smooth control transfer.
  - Teacher override: at each step, with prob beta, execute BC teacher action
    (teacher_net = BC weights, frozen) instead of DQN action → preserves temporal
    consistency of success trajectories (the exact thing replay+eps destroyed).
  - dagger_buffer: SEPARATE replay for (state, teacher_action) pairs (no pollution
    of DQN reward buffer).  BC cross-entropy loss pulls Q toward teacher action.
  - Mixed loss: TD (DQN replay) + lambda_dagger * CE (dagger buffer) + skill L2.

Sprint 40 T0 (train-eval protocol unification): eval uses GATE_BEHAVIORS 5-strategy
mixed protocol (random/aggressive/defensive/circler/counter × stable seeds, defensive
speed_scale 0.40) — same as V9 gate.  Training-time WR must track gate WR within 10pp.

Usage:
    python3 finetune_dqn_s40.py [--init-weights models/chase_teacher_bc_s38_v2.pt]
                                [--save-name chase_dqn_dagger_s40] [--episodes 1000]
                                [--eval-n 30] [--eval-every 50] [--seed 42]
"""

import argparse
import hashlib
import os
import random
import sys
import time
from collections import deque

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", ".."))
for _p in (_HERE, _REPO, os.path.join(_REPO, "simulation")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from common.config import Config
from common.agent import DQNAgent
from common.network import DQN as CommonDQN
from lightweight_env import LightweightBottleSumoEnv
from v9_gate_evaluator import OpponentStrategies

# ── Sprint 40 T0: unified GATE 5-strategy mix (random/aggressive/defensive/circler/counter) ──
GATE_MIX = ["random", "aggressive", "defensive", "circler", "counter"]


def _stable_seed(ep: int, name: str) -> int:
    """Deterministic seed protocol — identical to v9_gate_evaluator."""
    return int(hashlib.sha256(f"{ep}:{name}".encode()).hexdigest()[:8], 16)


class DaggerAgent(DQNAgent):
    """DQN + DAgger teacher override (S40 T1 prototype).

    Extends S39 SkillProtectedAgent:
      - freeze net.0 (fc1) — BC perception representation kept intact
      - L2 skill-protection on trainable params (bc_ref snapshot)
      - NEW: frozen teacher_net (BC weights) overrides actions with prob beta
      - NEW: dagger_buffer holds (state, teacher_action) for BC CE supervision
    """

    def __init__(self, cfg: Config, bc_weights: str, skill_lambda: float = 1e-3,
                 dagger_lambda: float = 1.0, dagger_lambda_end: float = None,
                 beta_start: float = 1.0, beta_end: float = 0.1,
                 dagger_buffer_size: int = 20000,
                 phase2_start: int = 2000, phase2_steps: int = 3000,
                 teacher_check_every: int = 10, teacher_check_prob: float = 0.5):
        super().__init__(cfg)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # ── BC warm-start (teacher init for BOTH q_net and teacher_net) ──
        bc_sd = torch.load(bc_weights, map_location="cpu", weights_only=True)
        self.q_net.load_state_dict(bc_sd)
        self.target_net.load_state_dict(bc_sd)

        # ── skill protection: freeze fc1 (net.0) + L2 on the rest ──
        self.skill_lambda = skill_lambda
        self.bc_ref = {}
        for name, p in self.q_net.named_parameters():
            if name.startswith("net.0."):
                p.requires_grad = False
            else:
                self.bc_ref[name] = p.detach().clone()
        self.bc_ref = {k: v.to(self.device) for k, v in self.bc_ref.items()}

        # ── DAgger teacher: frozen BC copy ──
        self.teacher_net = CommonDQN(
            cfg.state_dim, cfg.action_dim, cfg.hidden_dim, cfg.n_hidden
        ).to(self.device)
        self.teacher_net.load_state_dict(bc_sd)
        for p in self.teacher_net.parameters():
            p.requires_grad = False
        self.teacher_net.eval()

        # ── DAgger state ──
        self.beta_start = beta_start
        self.beta_end = beta_end
        self.beta = beta_start
        self.dagger_lambda = dagger_lambda
        self.dagger_lambda_start = dagger_lambda
        self.dagger_lambda_end = dagger_lambda_end if dagger_lambda_end is not None else dagger_lambda
        self.dagger_buffer = deque(maxlen=dagger_buffer_size)
        # ── S42 two-phase: phase2 = pure-RL tail (beta floored, lambda decays, teacher check) ──
        self.phase2_start = phase2_start          # steps after which beta annealing done
        self.phase2_steps = phase2_steps          # length of pure-RL tail
        self.teacher_check_every = teacher_check_every
        self.teacher_check_prob = teacher_check_prob

        # re-create optimizer AFTER freezing (frozen params excluded)
        self.optimizer = torch.optim.Adam(
            [p for p in self.q_net.parameters() if p.requires_grad],
            lr=cfg.learning_rate,
        )

    # ── DAgger action: beta-prob teacher override, else DQN epsilon-greedy ──
    def select_action(self, state: np.ndarray, training: bool = True) -> int:
        if training:
            # Phase-2 teacher check (T2 drift guard): every N steps, with prob p,
            # verify DQN choice against teacher; if disagree → follow teacher
            if (self.total_steps >= self.phase2_start
                    and self.total_steps % self.teacher_check_every == 0
                    and random.random() < self.teacher_check_prob):
                with torch.no_grad():
                    s_t = torch.FloatTensor(state).unsqueeze(0).to(self.device)
                    a_teacher = self.teacher_net(s_t).argmax(dim=1).item()
                    a_dqn = self.q_net(s_t).argmax(dim=1).item()
                if a_dqn != a_teacher:
                    return a_teacher  # periodic teacher verification
            if random.random() < self.beta:
                # Teacher override — preserves temporally-consistent pursuit behavior
                with torch.no_grad():
                    s_t = torch.FloatTensor(state).unsqueeze(0).to(self.device)
                    return self.teacher_net(s_t).argmax(dim=1).item()
        return super().select_action(state, training)

    def collect_teacher_action(self, state: np.ndarray) -> int:
        """Record (state, teacher_action) into dagger_buffer for BC supervision."""
        with torch.no_grad():
            s_t = torch.FloatTensor(state).unsqueeze(0).to(self.device)
            a_t = self.teacher_net(s_t).argmax(dim=1).item()
        self.dagger_buffer.append((state, a_t))
        return a_t

    # ── beta annealing (linear over steps, mirrors epsilon decay) ──
    def _anneal_beta(self):
        self.beta = max(
            self.beta_end,
            self.beta_start
            - self.total_steps
            * (self.beta_start - self.beta_end)
            / max(1, self.cfg.epsilon_decay),
        )
        # S42 phase-2: dagger_lambda decays ONLY after beta annealing done
        # (phase1 keeps lambda=1.0 to preserve skills; phase2 releases for pure RL)
        if self.dagger_lambda_end != self.dagger_lambda_start:
            if self.total_steps >= self.phase2_start:
                t_in_phase2 = self.total_steps - self.phase2_start
                frac = min(1.0, t_in_phase2 / max(1, self.phase2_steps))
                self.dagger_lambda = (
                    self.dagger_lambda_start
                    - frac * (self.dagger_lambda_start - self.dagger_lambda_end)
                )

    # ── mixed update: TD + dagger BC CE + skill L2 ──
    def update(self) -> float:
        loss_td = 0.0
        loss_bc = 0.0

        # 1) DQN TD loss
        if len(self.replay_buffer) >= self.cfg.batch_size:
            s, a, r, ns, d = self.replay_buffer.sample(self.cfg.batch_size)
            s, a, r, ns, d = (t.to(self.device) for t in (s, a, r, ns, d))
            q_values = self.q_net(s).gather(1, a.unsqueeze(1)).squeeze(1)
            with torch.no_grad():
                if self.cfg.use_double_dqn:
                    best_actions = self.q_net(ns).argmax(dim=1)
                    target_next = self.target_net(ns).gather(1, best_actions.unsqueeze(1)).squeeze(1)
                else:
                    target_next = self.target_net(ns).max(dim=1).values
                target = r + self.cfg.gamma * target_next * (1 - d)
            loss_td = F.smooth_l1_loss(q_values, target)

        # 2) DAgger BC CE loss (teacher actions as supervision)
        if len(self.dagger_buffer) >= self.cfg.batch_size:
            idxs = np.random.choice(
                len(self.dagger_buffer), self.cfg.batch_size, replace=False
            )
            batch = [self.dagger_buffer[i] for i in idxs]
            s_bc = torch.FloatTensor(np.array([b[0] for b in batch])).to(self.device)
            a_bc = torch.LongTensor([b[1] for b in batch]).to(self.device)
            logits = self.q_net(s_bc)
            loss_bc = F.cross_entropy(logits, a_bc)

        if loss_td == 0.0 and loss_bc == 0.0:
            return 0.0

        # 3) skill-protection L2 on trainable (non-frozen) params vs BC snapshot
        l2 = 0.0
        for name, p in self.q_net.named_parameters():
            if p.requires_grad and name in self.bc_ref:
                l2 = l2 + ((p - self.bc_ref[name]) ** 2).sum()
        l2 = self.skill_lambda * l2

        loss = loss_td + self.dagger_lambda * loss_bc + l2

        self.optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(
            [p for p in self.q_net.parameters() if p.requires_grad],
            self.cfg.clip_grad_norm,
        )
        self.optimizer.step()

        self.total_steps += 1
        self.epsilon = max(
            self.cfg.epsilon_end,
            self.cfg.epsilon_start
            - self.total_steps
            * (self.cfg.epsilon_start - self.cfg.epsilon_end)
            / self.cfg.epsilon_decay,
        )
        self._anneal_beta()

        if self.total_steps % self.cfg.target_update_freq == 0:
            self.target_net.load_state_dict(self.q_net.state_dict())

        return (loss_td + self.dagger_lambda * loss_bc).item()


# ── Sprint 40 T0: mixed GATE evaluation (5 strategies, stable seeds) ──
def mixed_gate_eval(agent, n_episodes: int = 30, verbose: bool = True) -> dict:
    """Evaluate against GATE_MIX 5-strategy protocol with stable seeds.

    Mirrors v9_gate_evaluator: per-strategy episodes, defensive speed_scale 0.40.
    This is the UNIFIED training-time eval — must track gate WR within 10pp.
    """
    per = len(GATE_MIX)
    per_strategy = n_episodes // per
    wins, total = 0, 0
    per_wins = {}
    for strat in GATE_MIX:
        s_wins = 0
        env = LightweightBottleSumoEnv(
            opponent_strategy=OpponentStrategies.get(strat),
            opponent_speed_scale=0.40 if strat == "defensive" else 1.0,
        )
        for i in range(per_strategy):
            seed = _stable_seed(i, strat)
            obs, _ = env.reset(seed=seed)
            done = False
            total_reward = 0.0
            while not done:
                with torch.no_grad():
                    s_t = torch.FloatTensor(obs).unsqueeze(0).to(agent.device)
                    action = agent.q_net(s_t).argmax(dim=1).item()
                obs, reward, done, truncated, _ = env.step(action)
                total_reward += reward
                if truncated:
                    done = True
            # win convention identical to v9_gate_evaluator: terminated and reward > 5
            if done and total_reward > 5.0:
                s_wins += 1
        wins += s_wins
        total += per_strategy
        per_wins[strat] = s_wins
        if verbose:
            print(f"    eval[{strat:10s}] {s_wins}/{per_strategy}")
    wr = wins / total if total else 0.0
    if verbose:
        print(f"  MixedEval: WR={wr:.1%} ({wins}/{total})  per_strategy={per_wins}")
    return {"wr": wr, "wins": wins, "total": total, "per_strategy": per_wins}


def run_dagger_episode(agent: DaggerAgent, env, cfg: Config, ep: int):
    """One training episode with DAgger teacher override + dagger buffer fill."""
    obs, _ = env.reset()
    done = False
    ep_reward = 0.0
    steps = 0
    while not done:
        # record teacher action for BC supervision (every step, regardless of override)
        agent.collect_teacher_action(obs)
        action = agent.select_action(obs, training=True)
        next_obs, reward, done, truncated, _ = env.step(action)
        reward = np.clip(reward, -100.0, 100.0)
        agent.replay_buffer.push(obs, action, reward, next_obs, float(done))
        agent.update()
        obs = next_obs
        ep_reward += reward
        steps += 1
        if truncated:
            done = True
    return ep_reward, steps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="quick_test")
    ap.add_argument("--init-weights", default="models/chase_teacher_bc_s38_v2.pt")
    ap.add_argument("--save-name", default="chase_dqn_s42")
    ap.add_argument("--episodes", type=int, default=1000)
    ap.add_argument("--eval-n", type=int, default=30, help="mixed-eval episodes (5 strategies × n/5)")
    ap.add_argument("--eval-every", type=int, default=50)
    ap.add_argument("--skill-lambda", type=float, default=1e-3)
    ap.add_argument("--dagger-lambda", type=float, default=1.0)
    ap.add_argument("--beta-start", type=float, default=1.0)
    ap.add_argument("--beta-end", type=float, default=0.1)
    # S42 two-phase (pure-RL tail):
    ap.add_argument("--lambda-tail", type=float, default=0.3,
                    help="T1: dagger_lambda target in phase2 (pure-RL tail); <0 disables phase2")
    ap.add_argument("--phase2-steps", type=int, default=3000,
                    help="T1: length of phase2 pure-RL tail (steps after beta annealing done)")
    ap.add_argument("--teacher-check-every", type=int, default=10,
                    help="T2: teacher verification interval in phase2 (steps)")
    ap.add_argument("--teacher-check-prob", type=float, default=0.5,
                    help="T2: prob of teacher verification when interval hits")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    cfg = Config.quick_test()
    cfg.n_episodes = args.episodes
    cfg.save_name = args.save_name
    cfg.epsilon_start = 0.05
    cfg.epsilon_end = 0.01
    cfg.epsilon_decay = args.episodes * 2  # anneal over 2× episodes-worth of steps

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    if not os.path.isfile(args.init_weights):
        raise FileNotFoundError(f"init_weights not found: {args.init_weights}")

    print(f"╔{'═' * 64}╗")
    print(f"║  Sprint 42: pure-RL tail after DAgger (T1) + drift guard (T2)  ║")
    print(f"╚{'═' * 64}╝")
    print(f"  init: {args.init_weights}")
    print(f"  beta: {args.beta_start} → {args.beta_end} (linear over {cfg.epsilon_decay} steps)")
    if args.lambda_tail >= 0:
        print(f"  phase2 (pure-RL tail): lambda {args.dagger_lambda} → {args.lambda_tail}"
              f" over {args.phase2_steps} steps, teacher-check every {args.teacher_check_every}"
              f" (p={args.teacher_check_prob})")
    else:
        print("  phase2: DISABLED (S40 baseline behavior)")
    print(f"  skill_lambda={args.skill_lambda}  epsilon: {cfg.epsilon_start} → {cfg.epsilon_end} | episodes: {args.episodes}")

    agent = DaggerAgent(
        cfg, args.init_weights,
        skill_lambda=args.skill_lambda,
        dagger_lambda=args.dagger_lambda,
        dagger_lambda_end=args.lambda_tail if args.lambda_tail >= 0 else None,
        beta_start=args.beta_start,
        beta_end=args.beta_end,
        phase2_start=cfg.epsilon_decay,  # beta annealing done → phase2 begins
        phase2_steps=args.phase2_steps,
        teacher_check_every=args.teacher_check_every,
        teacher_check_prob=args.teacher_check_prob,
    )

    # curriculum: 13-slot weighted round-robin (gate×2 + speed ladder×1) — S37 protocol
    curriculum_pool = (
        ["random", "aggressive", "defensive", "circler", "counter"] * 2
        + ["moderate", "passive", "stationary"]
    )

    best_wr = -1.0
    t0 = time.time()
    for ep in range(1, args.episodes + 1):
        strat = curriculum_pool[(ep - 1) % len(curriculum_pool)]
        env = LightweightBottleSumoEnv(
            opponent_strategy=OpponentStrategies.get(strat),
            opponent_speed_scale=0.40 if strat == "defensive" else 1.0,
        )
        ep_reward, steps = run_dagger_episode(agent, env, cfg, ep)
        if ep % 10 == 0 or ep == 1:
            print(
                f"  Ep {ep:5d}/{args.episodes} opp={strat:10s} R={ep_reward:7.1f} "
                f"steps={steps:3d} eps={agent.epsilon:.3f} β={agent.beta:.2f} "
                f"λd={agent.dagger_lambda:.2f}",
                flush=True,
            )
        if ep % args.eval_every == 0:
            print(f"  ── MixedEval @ ep {ep} (T0 protocol) ──", flush=True)
            res = mixed_gate_eval(agent, n_episodes=args.eval_n)
            if res["wr"] > best_wr:
                best_wr = res["wr"]
                agent.save(f"models/{args.save_name}.pt.best")
                print(f"  ★ best WR={res['wr']:.1%} → saved .best", flush=True)

    print(f"  Training done in {time.time()-t0:.1f}s. Final mixed eval:")
    final = mixed_gate_eval(agent, n_episodes=args.eval_n)
    agent.save(f"models/{args.save_name}.pt")
    print(f"  Final WR={final['wr']:.1%} ({final['wins']}/{final['total']}) best={best_wr:.1%}")
    print(f"  Saved: models/{args.save_name}.pt  (+ .best)")
    print(f"  β final={agent.beta:.3f} eps final={agent.epsilon:.4f}")


if __name__ == "__main__":
    main()
