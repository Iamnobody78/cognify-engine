"""Sprint 60/61: Distill S59-optimized heuristic (V9RuleAgent, 100% gate) into NanoQNet9 MLP.

Teacher = V9RuleAgent(force_heuristic=True) — CURRENT code (contains S59 fixes:
TR-004/vectored, charge tightening, edge_f_turn lateral escape).
Student  = NanoQNet9 (S44 architecture, 9→hidden→21 MLP, BC cross-entropy).
Curriculum = 13-slot course (same split as S44: 11 opponents-slots + 2 random).
Validation = v9_gate_evaluator.py --policy nano (S45 dual-track deployment).

S61 (R0 research loop, I1 from TORL-VLA arXiv:2606.09337):
intervention-censored distillation — teacher GUARD branches (SR-001/* edge
escape, TR-004/vectored_* curve) are teacher "interventions", not policy
decisions. Down-weight those samples during BC (--intervention-weight)
so the student doesn't mimic guard-triggered reflexes as if they were
the policy's own decisions (TORL-VLA intervention-censored critic analog).

Run: python3 simulation/training/distill_s60_heuristic.py [--episodes 400] [--hidden 16|24] [--intervention-weight 0.25]
"""
import argparse
import os
import random
import sys
import time
from collections import Counter

import numpy as np
import torch
import torch.nn as nn

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from simulation.lightweight_env import LightweightBottleSumoEnv
from simulation.v9_gate_evaluator import (V9RuleAgent, OpponentStrategies,
                                          MAX_STEPS_PER_EPISODE)
from simulation.training.distill_chase_s44 import NanoQNet9  # reuse S44 architecture

# ── 13-slot curriculum (mirrors S44: opponents + 2 random slots) ────────────
def _curriculum():
    names = ["aggressive", "defensive", "circler", "counter"]
    slots = [n for n in names for _ in range(2)]  # 8 opponent slots
    slots += ["random", "random"]                 # +2 random slots (total 10)
    # fill to 13 with a second pass of the 4 named + random
    slots += ["random", "aggressive", "defensive"]
    return slots[:13]


# ── S61 I1 (TORL-VLA intervention-censored analog) ─────────────────────────
# Teacher branches that are SAFETY/EVASION *interventions* (edge escapes, curve
# dodges), not strategic policy decisions. In real systems, intervention
# success must NOT be credited to the policy action that preceded it; here we
# down-weight these samples so the student learns the strategic policy, not a
# mimicry of guard reflexes.
GUARD_BRANCHES = {
    "SR-001/edge_f", "SR-001/edge_f_turn", "SR-001/edge_l",
    "SR-001/edge_r", "SR-001/edge_b",
    "TR-004/vectored_l", "TR-004/vectored_r",
}


def collect_demos(env_fn, agent, n_episodes, seed=2026):
    """Run teacher (heuristic) across a 13-slot curriculum; record (obs9, action, guard).

    Returns X, Y, guard_mask where guard_mask[i]=True means sample i came from
    a teacher guard/intervention branch (S61 I1).

    Efficiency: build ONE env per opponent (strategy fixed at construction),
    run all that opponent's episodes on it, then move to next opponent.
    Avoids O(episodes) env rebuilds (teacher construction dominates cost).
    """
    X, Y, G = [], [], []
    cur = _curriculum()
    # group episodes by opponent: [opp0]*n, [opp1]*n ... (round-robin per slot)
    slot_eps = (n_episodes + len(cur) - 1) // len(cur)
    plan = []
    for si, opp_name in enumerate(cur):
        lo = si * slot_eps
        hi = min((si + 1) * slot_eps, n_episodes)
        if hi > lo:
            plan.append((opp_name, lo, hi))
    wins = 0
    done_eps = 0
    for opp_name, lo, hi in plan:
        env = env_fn(opp_name)
        for ep in range(lo, hi):
            obs, _ = env.reset(seed=seed + ep)
            done = False
            while not done:
                obs_list = obs.tolist() if hasattr(obs, "tolist") else list(obs)
                # traced select_action exposes heuristic branch for guard marking
                a, trace = agent.select_action_traced(obs_list)
                branch = trace.get("branch", "")
                X.append(np.asarray(obs, dtype=np.float32))
                Y.append(a)
                G.append(branch in GUARD_BRANCHES)
                obs, reward, terminated, truncated, _ = env.step(a)
                done = terminated or truncated
            if terminated and reward > 5:
                wins += 1
            done_eps += 1
            if done_eps % 50 == 0:
                print(f"  [collect] ep={done_eps}/{n_episodes} wins={wins} samples={len(X)}")
    guard_frac = float(np.mean(G)) if G else 0.0
    print(f"  [collect] guard/intervention fraction={guard_frac:.3f} "
          f"({int(guard_frac*len(G))}/{len(G)})")
    return np.array(X), np.array(Y, dtype=np.int64), np.array(G, dtype=bool), wins


def train(X, Y, G, hidden_dim, epochs=60, batch_size=128, lr=1e-3, seed=7,
          intervention_weight=0.25):
    """BC with intervention-censored weighting (S61 I1).

    Samples from teacher guard branches get loss weight `intervention_weight`
    (< 1.0): student learns the strategic policy; guard reflexes are not
    mimicked as if they were deliberate decisions. weight=1.0 → plain S60 BC.
    """
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)
    n = X.shape[0]
    idx = np.random.permutation(n)
    n_train = int(n * 0.9)
    Xtr, Ytr, Gtr = X[idx[:n_train]], Y[idx[:n_train]], G[idx[:n_train]]
    Xva, Yva = X[idx[n_train:]], Y[idx[n_train:]]

    # per-sample loss weight: 1.0 for policy samples, w for guard samples
    Wtr = np.where(Gtr, intervention_weight, 1.0).astype(np.float32)

    model = NanoQNet9(hidden_dim=hidden_dim, n_hidden=2)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.CrossEntropyLoss(reduction="none")

    Xt = torch.FloatTensor(Xtr)
    Yt = torch.LongTensor(Ytr)
    Wt = torch.FloatTensor(Wtr)
    Xv = torch.FloatTensor(Xva)
    Yv = torch.LongTensor(Yva)

    for ep in range(epochs):
        model.train()
        perm = torch.randperm(Xt.size(0))
        tot = 0.0
        for i in range(0, Xt.size(0), batch_size):
            bi = perm[i:i + batch_size]
            out = model(Xt[bi])
            loss = (loss_fn(out, Yt[bi]) * Wt[bi]).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot += loss.item() * bi.size(0)
        # validation accuracy
        model.eval()
        with torch.no_grad():
            pred = model(Xv).argmax(dim=1)
            acc = (pred == Yv).float().mean().item()
        if (ep + 1) % 10 == 0:
            print(f"  [train] ep={ep+1}/{epochs} loss={tot/Xt.size(0):.4f} val_acc={acc:.3f}")
    return model


def benchmark_latency(heuristic_agent, model, obs, iters=1000):
    """Median select_action latency: heuristic rule chain vs MLP forward."""
    import statistics
    import time as _t

    # heuristic (rule chain)
    t0 = _t.perf_counter()
    for _ in range(iters):
        heuristic_agent.select_action(obs)
    t_h = (_t.perf_counter() - t0) / iters

    # MLP forward
    x = torch.FloatTensor(np.asarray(obs, dtype=np.float32)).unsqueeze(0)
    model.eval()
    with torch.no_grad():
        t0 = _t.perf_counter()
        for _ in range(iters):
            _ = model(x).argmax(dim=1)
        t_m = (_t.perf_counter() - t0) / iters

    n_params = sum(p.numel() for p in model.parameters())
    return t_h, t_m, n_params


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=400)
    ap.add_argument("--hidden", type=int, default=24)
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--intervention-weight", type=float, default=0.25,
                    help="BC loss weight for teacher GUARD branches (S61 I1); "
                         "1.0 = plain S60 BC")
    ap.add_argument("--out", type=str, default="models/nano_s60.pt")
    args = ap.parse_args()

    env = LightweightBottleSumoEnv(opponent_strategy=OpponentStrategies().get("aggressive"),
                                   opponent_speed_scale=0.40)
    teacher = V9RuleAgent(force_heuristic=True)

    def env_fn(opp_name):
        opp = OpponentStrategies().get(opp_name)
        speed_scale = 0.40 if opp_name == "defensive" else 1.0
        return LightweightBottleSumoEnv(opponent_strategy=opp,
                                        opponent_speed_scale=speed_scale)

    t0 = time.time()
    print(f"[S61-I1] collecting demos: {args.episodes} eps, teacher=heuristic(S59)...")
    X, Y, G, wins = collect_demos(env_fn, teacher, args.episodes)
    print(f"[S61-I1] collected {X.shape[0]} samples, teacher wins={wins}/{args.episodes} "
          f"({time.time()-t0:.0f}s)")

    # action distribution sanity
    top = Counter(Y.tolist()).most_common(8)
    print(f"[S61-I1] action dist top: {top}")

    print(f"[S61-I1] training NanoQNet9(hidden={args.hidden}) "
          f"intervention_weight={args.intervention_weight} ...")
    model = train(X, Y, G, args.hidden, epochs=args.epochs,
                  intervention_weight=args.intervention_weight)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    torch.save(model.state_dict(), args.out)
    print(f"[S61-I1] saved {args.out}")

    # latency benchmark on a representative mid-engagement obs
    sample_obs = [0.55, 0.55, 0.55, 0.55, 0.42, 0.05, 0.1, 0.2, -0.1]
    t_h, t_m, n_params = benchmark_latency(teacher, model, sample_obs, iters=1000)
    print(f"[S61-I1] latency: heuristic={t_h*1e6:.1f}us  MLP={t_m*1e6:.1f}us  "
          f"speedup={t_h/t_m:.1f}x  params={n_params}")


if __name__ == "__main__":
    main()
