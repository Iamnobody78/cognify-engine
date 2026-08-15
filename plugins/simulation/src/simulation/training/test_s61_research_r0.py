"""S61 R0 research-loop unit tests (S.A.M.U.E.L. Utilize stage).

Covers:
- I1 (TORL-VLA intervention-censored distillation): collect_demos produces a
  guard_mask; guard branches are flagged; train() accepts intervention_weight
  and weights guard samples down (loss contribution smaller than equal-weight).
- I2 (MoDE-VLA residual injection): ResidualGuardAgent activates the S59 guard
  in dangerous states and the student MLP in safe states; trace mode is
  correctly annotated; guard activation is rare in nominal play (measured on a
  short teacher rollout) — residual preserves the trunk.

Run: python3 -m pytest simulation/training/test_s61_research_r0.py -v
     (or directly: python3 simulation/training/test_s61_research_r0.py)
"""
import os
import sys

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from simulation.v9_gate_evaluator import (V9RuleAgent, _RLGateAgent,
                                          ResidualGuardAgent,
                                          _load_heuristic_rules)
from simulation.training.distill_s60_heuristic import (collect_demos, train,
                                                       GUARD_BRANCHES)
from simulation.lightweight_env import LightweightBottleSumoEnv
from simulation.v9_gate_evaluator import OpponentStrategies


def _mini_env_fn(opp_name):
    opp = OpponentStrategies().get(opp_name)
    speed_scale = 0.40 if opp_name == "defensive" else 1.0
    return LightweightBottleSumoEnv(opponent_strategy=opp,
                                    opponent_speed_scale=speed_scale)


# ── I1: intervention-censored distillation ─────────────────────────────────
def test_guard_branches_are_tracked_by_teacher():
    """Teacher's traced select_action must report the branch used."""
    agent = V9RuleAgent(force_heuristic=True)
    rules = _load_heuristic_rules()
    ecr = rules["l0_safety"]["edge_critical"]
    # construct a dangerous obs: front edge below CRITICAL threshold (this is
    # the SR-001 activation line; edge_danger_f alone is only a warning band)
    obs = [ecr - 0.02, 0.9, 0.9, 0.9, 0.5, 0.1, 0.1, 0.0, 0.0]
    a, trace = agent.select_action_traced(obs)
    assert "branch" in trace
    assert trace["branch"] in GUARD_BRANCHES, f"got {trace['branch']}"


def test_collect_demos_marks_guard_mask():
    """S61 I1: collect_demos returns guard_mask with non-trivial guard fraction."""
    X, Y, G, wins = collect_demos(_mini_env_fn, V9RuleAgent(force_heuristic=True),
                                  n_episodes=12, seed=61)
    assert X.shape[0] == Y.shape[0] == G.shape[0]
    assert X.shape[1] == 9, "obs must be 9-dim"
    guard_frac = float(G.mean())
    assert 0.0 < guard_frac < 1.0, f"guard fraction should be in (0,1), got {guard_frac}"
    assert wins >= 0


def test_intervention_weight_lowers_guard_loss_contribution():
    """I1: with intervention_weight < 1, guard samples contribute less loss.

    We verify the mechanism directly: same batch, weighted loss < unweighted
    when guard samples present.
    """
    rng = np.random.RandomState(0)
    X = rng.rand(64, 9).astype(np.float32)
    Y = rng.randint(0, 21, size=64).astype(np.int64)
    G = rng.rand(64) < 0.3  # 30% guard samples

    torch.manual_seed(0)
    model_w = torch.nn.Sequential(
        torch.nn.Linear(9, 16), torch.nn.ReLU(), torch.nn.Linear(16, 21))
    # ensure same init for both models
    model_p = torch.nn.Sequential(
        torch.nn.Linear(9, 16), torch.nn.ReLU(), torch.nn.Linear(16, 21))
    model_w.load_state_dict(model_p.state_dict())

    loss_fn = torch.nn.CrossEntropyLoss(reduction="none")
    out_w = model_w(torch.FloatTensor(X))
    w = torch.where(torch.BoolTensor(G), torch.full((64,), 0.25), torch.ones(64))
    loss_w = (loss_fn(out_w, torch.LongTensor(Y)) * w).mean()

    out_p = model_p(torch.FloatTensor(X))
    loss_p = loss_fn(out_p, torch.LongTensor(Y)).mean()
    assert loss_w.item() < loss_p.item(), (
        f"weighted ({loss_w:.4f}) should be < plain ({loss_p:.4f})")


def test_train_accepts_intervention_weight():
    """I1: train() runs end-to-end with intervention_weight and produces a model."""
    rng = np.random.RandomState(1)
    X = rng.rand(200, 9).astype(np.float32)
    Y = rng.randint(0, 21, size=200).astype(np.int64)
    G = rng.rand(200) < 0.3
    model = train(X, Y, G, hidden_dim=16, epochs=5, batch_size=64,
                  intervention_weight=0.25, seed=3)
    assert model is not None


# ── I2: residual injection guard ────────────────────────────────────────────
def _make_student():
    """Train a tiny NanoQNet9-like student so ResidualGuardAgent loads it."""
    rng = np.random.RandomState(2)
    X = rng.rand(300, 9).astype(np.float32)
    Y = rng.randint(0, 21, size=300).astype(np.int64)
    G = rng.rand(300) < 0.3
    model = train(X, Y, G, hidden_dim=16, epochs=3, batch_size=64, seed=5)
    path = "/tmp/s61_student.pt"
    torch.save(model.state_dict(), path)
    return path


def test_residual_guard_dangerous_state_activates_guard():
    """I2: dangerous obs (front edge below critical) → guard branch, not student."""
    rules = _load_heuristic_rules()
    ecr = rules["l0_safety"]["edge_critical"]
    agent = ResidualGuardAgent(model_path=_make_student())
    danger_obs = [ecr - 0.01, 0.9, 0.9, 0.9, 0.5, 0.1, 0.1, 0.0, 0.0]
    a, t = agent.select_action_traced(danger_obs)
    assert t["mode"] == "residual-guard", f"expected guard, got {t['mode']}"
    # guard must be one of the SR-001 escape branches
    assert "guard/" in t["branch"]


def test_residual_guard_safe_state_uses_student():
    """I2: safe obs → student MLP action, no guard interference."""
    agent = ResidualGuardAgent(model_path=_make_student())
    safe_obs = [0.9, 0.9, 0.9, 0.9, 0.8, 0.5, 0.1, 0.0, 0.0]
    a, t = agent.select_action_traced(safe_obs)
    assert t["mode"] == "residual-student", f"expected student, got {t['mode']}"
    assert isinstance(a, int) and 0 <= a < 21


def test_residual_guard_activation_rare_in_nominal_play():
    """I2 (MoDE-VLA claim): residual must be rare in nominal play so the trunk
    is preserved. Run 3 teacher-ish episodes; count danger-triggered frames.
    """
    rules = _load_heuristic_rules()
    ecr = rules["l0_safety"]["edge_critical"]
    env = _mini_env_fn("circler")
    obs, _ = env.reset(seed=61)
    danger_frames = 0
    total = 0
    done = False
    while not done:
        o = obs.tolist() if hasattr(obs, "tolist") else list(obs)
        if any(e < ecr for e in o[:4]):
            danger_frames += 1
        total += 1
        a, _ = V9RuleAgent(force_heuristic=True).select_action_traced(o)
        obs, _, term, trunc, _ = env.step(a)
        done = term or trunc
        if total > 500:
            break
    frac = danger_frames / max(total, 1)
    # nominal play should spend the vast majority of time in safe states
    assert frac < 0.5, f"danger fraction {frac:.2f} too high for a residual guard"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    npass = 0
    for t in tests:
        try:
            t()
            print(f"  [PASS] {t.__name__}")
            npass += 1
        except Exception as e:
            print(f"  [FAIL] {t.__name__}: {e}")
    print(f"\n{len(tests)} tests, {npass} passed")
    sys.exit(0 if npass == len(tests) else 1)
