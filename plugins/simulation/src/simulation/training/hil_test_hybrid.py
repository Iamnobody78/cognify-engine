"""
hil_test_hybrid.py — HIL verification for Hybrid DQN-TD3 STM32 deployment

Usage:
    python hil_test_hybrid.py --weights stm32_deploy/stm32_weights.h --verify-only
    python hil_test_hybrid.py --weights stm32_deploy/stm32_weights.h --episodes 100
"""
from __future__ import annotations

import argparse, json, re, sys, time
from pathlib import Path
from datetime import datetime
from typing import Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.resolve()))

from bottlesumo_pi.simulation.continuous_env import ContinuousBottleSumoEnv
from bottlesumo_pi.common.hybrid_agent import HybridAgent, HybridConfig


class PyTorchReference:
    def __init__(self):
        cfg = HybridConfig(device="cpu")
        self.agent = HybridAgent(cfg)
        self.agent.eval()

    def infer(self, obs):
        s, a = self.agent.act(obs, explore=False)
        return s, a


class CArrayReference:
    """Parse stm32_weights.h and run C-equivalent inference in Python."""

    def __init__(self, weights_path: str):
        text = Path(weights_path).read_text(encoding="utf-8")
        text = re.sub(r'/\*.*?\*/', ' ', text, flags=re.DOTALL)
        text = re.sub(r'//[^\n]*', ' ', text)
        self.text = text
        self._load_arrays()

    def _find_array(self, name: str) -> np.ndarray:
        for prefix in [f"_{name}", name]:
            pat = re.escape(f"static const float {prefix}[") + r'\d+\]\s*=\s*\{'
            m = re.search(pat, self.text)
            if m:
                break
        if not m:
            raise ValueError(f"Array not found: {name}")
        start = m.end()
        depth = 1
        i = start
        while i < len(self.text) and depth > 0:
            if self.text[i] == '{': depth += 1
            elif self.text[i] == '}': depth -= 1
            i += 1
        raw = self.text[start:i-1]
        vals = []
        for t in re.split(r'[,\s]+', raw):
            t = t.strip().rstrip('f')
            if t:
                try: vals.append(float(t))
                except ValueError: pass
        return np.array(vals, dtype=np.float32)

    def _load_arrays(self):
        def arr(name): return self._find_array(name)
        def mat(name, r, c): return arr(name).reshape(r, c)

        self.l0_w = mat("DQN_L0_W", 128, 7)
        self.l0_b = arr("DQN_L0_B")
        self.l1_w = mat("DQN_L1_W", 128, 128)
        self.l1_b = arr("DQN_L1_B")
        self.l2_w = mat("DQN_L2_W", 4, 128)
        self.l2_b = arr("DQN_L2_B")
        self.emb = mat("ACTOR_EMB", 4, 4)
        self.a0_w = mat("ACTOR_L0_W", 256, 11)
        self.a0_b = arr("ACTOR_L0_B")
        self.a1_w = mat("ACTOR_L1_W", 256, 256)
        self.a1_b = arr("ACTOR_L1_B")
        self.a2_w = mat("ACTOR_L2_W", 2, 256)
        self.a2_b = arr("ACTOR_L2_B")

    def _relu(self, x): return np.maximum(x, 0)

    def infer(self, obs):
        # DQN
        h = self._relu(self.l0_w @ obs + self.l0_b)
        h = self._relu(self.l1_w @ h + self.l1_b)
        s = int(np.argmax(self.l2_w @ h + self.l2_b))
        # Actor
        x = np.concatenate([obs, self.emb[s]])
        h = self._relu(self.a0_w @ x + self.a0_b)
        h = self._relu(self.a1_w @ h + self.a1_b)
        raw = np.tanh(self.a2_w @ h + self.a2_b)
        ll, lh, al, ah = -0.7, 0.7, -5.0, 5.0
        a = np.zeros(2, np.float32)
        a[0] = (raw[0] + 1) * 0.5 * (lh - ll) + ll
        a[1] = (raw[1] + 1) * 0.5 * (ah - al) + al
        return s, a


def verify(ref_c, ref_pt, n=500):
    """Check inference correctness. Only valid when both use SAME trained model."""
    matches, errs = 0, []
    rng = np.random.RandomState(42)
    for _ in range(n):
        obs = rng.uniform(0, 1, 7).astype(np.float32)
        try:
            sc, ac = ref_c.infer(obs)
            sp, ap = ref_pt.infer(obs)
            if sc == sp: matches += 1
            errs.append(np.max(np.abs(ac - ap)))
        except Exception:
            pass

    # Note: random init models will differ — this is expected.
    # Agreement only expected with trained model exports.
    is_same_model = matches / n > 0.95

    return {
        "n": len(errs), "strategy_agree": matches / max(n, 1),
        "max_err": float(np.max(errs)) if errs else 0,
        "mean_err": float(np.mean(errs)) if errs else 0,
        "pass": is_same_model and (np.max(errs) if errs else 0) < 0.01,
        "note": "Random init models differ; use trained model for correctness check."
    }


def run_game(ref, ep=100):
    env = ContinuousBottleSumoEnv(opponent_profile="aggressive", seed=42)
    rewards, wins = [], 0
    t_total, n_inf = 0.0, 0
    for _ in range(ep):
        obs, _ = env.reset(); er = 0.0; d = False; tr = False
        while not (d or tr):
            t0 = time.perf_counter()
            s, a = ref.infer(obs)
            t1 = time.perf_counter()
            t_total += (t1 - t0) * 1e6
            n_inf += 1
            obs, r, d, tr, _ = env.step(a)
            er += r
        rewards.append(er)
        if er > 0: wins += 1
    env.close()
    return {"episodes": ep, "mean_reward": float(np.mean(rewards)),
            "win_rate": wins/ep, "avg_inference_us": t_total/n_inf,
            "n_inferences": n_inf}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--weights", default="stm32_deploy/stm32_weights.h")
    p.add_argument("--episodes", type=int, default=100)
    p.add_argument("--verify-only", action="store_true")
    p.add_argument("-o", default="reports/hil_test")
    args = p.parse_args()

    wp = Path(args.weights)
    if not wp.exists():
        print(f"[ERROR] Not found: {wp}")
        sys.exit(1)

    print("=" * 60)
    print(" HIL Verification — Hybrid DQN-TD3")
    print("=" * 60)

    print("\n[1/3] Inference correctness...")
    ref_c = CArrayReference(str(wp))
    ref_pt = PyTorchReference()
    v = verify(ref_c, ref_pt)
    print(f"  Strategy agreement: {v['strategy_agree']:.1%}")
    print(f"  Max action error:   {v['max_err']:.6f}")
    print(f"  Mean action error:  {v['mean_err']:.6f}")
    print(f"  Status: {'PASS' if v['pass'] else 'FAIL'}")

    if args.verify_only:
        sys.exit(0 if v["pass"] else 1)

    print(f"\n[2/3] Game simulation ({args.episodes} episodes)...")
    g = run_game(ref_c, args.episodes)
    print(f"  Mean reward: {g['mean_reward']:.1f}")
    print(f"  Win rate:    {g['win_rate']:.1%}")
    lat_pass = g['avg_inference_us'] < 200
    print(f"  Avg latency: {g['avg_inference_us']:.1f} us ({'PASS' if lat_pass else 'FAIL'})")

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out = Path(args.o) / stamp
    out.mkdir(parents=True, exist_ok=True)
    rpt = {"timestamp": stamp, "verify": v, "game": g, "pass": v["pass"] and lat_pass}
    with open(out / "hil_report.json", "w", encoding="utf-8") as f:
        json.dump(rpt, f, indent=2)
    print(f"\n[3/3] Report: {out / 'hil_report.json'}")
    print(f"\n{'='*60}\n  {'ALL CHECKS PASSED' if rpt['pass'] else 'CHECKS FAILED'}\n{'='*60}")
