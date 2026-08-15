"""
verify_int8_quant.py — CMSIS-NN q7_t post-training quantization accuracy (v4)

CRITICAL FIX: Actual V10 architecture is 7->128->128->128->21 (4 Linear layers).
Previous versions extracted weights from wrong layers.

Model: V10 bayesopt DQN (4 linear, n_hidden=2 per DQN class convention = 4 Linear total)
"""

import argparse
import json
import os
import sys

import numpy as np
import torch

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from bottlesumo_pi.common.network import DQN  # noqa: E402

# ═══════════════════════════════════════════════════════════════════
# Model
# ═══════════════════════════════════════════════════════════════════


def load_model(path: str) -> DQN:
    """Load DQN. n_hidden=2 per class convention = 4 Linear layers total."""
    model = DQN(obs_dim=7, action_dim=21, hidden_dim=128, n_hidden=2)
    state = torch.load(path, map_location="cpu", weights_only=False)
    model.load_state_dict(state)
    model.eval()
    return model


def extract_weights(model: DQN):
    """Extract all 4 linear layers. Sequential: [L0, ReLU, L1, ReLU, L2, ReLU, L3]."""
    layers = list(model.net.children())
    linear_layers = [layer for layer in layers if isinstance(layer, torch.nn.Linear)]
    assert len(linear_layers) == 4, f"Expected 4 Linear layers, got {len(linear_layers)}"
    w = [layer.weight.detach().numpy() for layer in linear_layers]
    b = [layer.bias.detach().numpy() for layer in linear_layers]
    return list(zip(w, b, strict=False))  # [(w1,b1), (w2,b2), (w3,b3), (w4,b4)]


# ═══════════════════════════════════════════════════════════════════
# Quantization
# ═══════════════════════════════════════════════════════════════════


def quantize_symmetric(t: np.ndarray):
    """Symmetric int8 quantization. Returns (q7_array, scale)."""
    mx = float(max(np.max(np.abs(t)), 1e-8))
    s = mx / 127.0
    q = np.clip(np.round(t / s), -128, 127).astype(np.int8)
    return q, s


def decompose_requant(requant: float):
    """Decompose requant_factor = mult * 2^{-shift}, mult in [0.5,1)*2^31."""
    if requant < 1e-30:
        return np.int64(0), np.int32(0)
    r, n = float(requant), np.int32(0)
    while r >= 1.0:
        r *= 0.5
        n += 1
    while r < 0.5:
        r *= 2.0
        n -= 1
    mult = np.int64(round(r * 2147483648.0))
    return max(mult, np.int64(1)), n


# ═══════════════════════════════════════════════════════════════════
# Calibration
# ═══════════════════════════════════════════════════════════════════


def run_layers(model, batch):
    """Forward pass, return post-ReLU activations for layers 0-2, and final output."""
    layers = list(model.net.children())
    linear_indices = [i for i, layer in enumerate(layers) if isinstance(layer, torch.nn.Linear)]
    x = torch.tensor(batch, dtype=torch.float32)
    with torch.no_grad():
        # L0: 7->128
        h0_pre = layers[linear_indices[0]](x).numpy()
        h0 = np.maximum(h0_pre, 0)
        # L1: 128->128
        h1_pre = layers[linear_indices[1]](torch.tensor(h0)).numpy()
        h1 = np.maximum(h1_pre, 0)
        # L2: 128->128
        h2_pre = layers[linear_indices[2]](torch.tensor(h1)).numpy()
        h2 = np.maximum(h2_pre, 0)
        # L3: 128->21
        out = layers[linear_indices[3]](torch.tensor(h2)).numpy()
    return [h0, h1, h2], out  # post-ReLU hidden + final Q


def calibrate(model, calib_batch, percentile=99.9):
    """Calibrate output scales for each layer's post-activation."""
    hiddens, q_vals = run_layers(model, calib_batch)
    scales = {}
    for i, h in enumerate(hiddens):
        clip = float(np.percentile(np.abs(h), percentile))
        scales[f"h{i}"] = max(clip / 127.0, 1e-6)
    # Q-values: use 100th percentile (max) to avoid saturation on final output
    clip_q = float(np.max(np.abs(q_vals)))
    scales["q"] = max(clip_q / 127.0, 1e-6)
    return scales


# ═══════════════════════════════════════════════════════════════════
# INT8 inference (4 layers)
# ═══════════════════════════════════════════════════════════════════


def int8_inference(state_f32, q_weights, w_scales, out_scales):
    """4-layer CMSIS-NN style INT8 inference.

    Architecture: 7->128->128->128->21
    All hidden layers use ReLU. Output layer has no activation.
    """
    (qw0, qb0), (qw1, qb1), (qw2, qb2), (qw3, qb3) = q_weights
    sw0, sw1, sw2, sw3 = w_scales
    os_h0, os_h1, os_h2 = out_scales["h0"], out_scales["h1"], out_scales["h2"]
    os_q = out_scales["q"]

    # ── Input quantization ──
    in_max = max(float(np.max(np.abs(state_f32))), 0.01)
    in_scale = in_max / 127.0
    q_in = np.clip(np.round(state_f32 / in_scale), -128, 127).astype(np.int8)

    def requantize_accum(acc, in_s, w_s, out_s):
        """Requantize int64 accumulator to int8 [-128,127]."""
        if in_s < 1e-30 or out_s < 1e-30:
            return np.int8(0)
        rf = (in_s * w_s) / out_s
        mult, shift = decompose_requant(rf)
        if mult == 0:
            return np.int8(0)
        val = (np.int64(acc) * mult) >> (31 - int(shift))
        return np.int8(np.clip(val, -128, 127))

    # ── Layer 0: 7→128 ──
    q_h0 = np.zeros(128, dtype=np.int8)
    for i in range(128):
        acc = np.int64(qb0[i])
        for j in range(7):
            acc += np.int64(q_in[j]) * np.int64(qw0[i, j])
        if acc <= 0:
            q_h0[i] = 0
        else:
            q_h0[i] = requantize_accum(acc, in_scale, sw0, os_h0)

    # ── Layer 1: 128→128 ──
    q_h1 = np.zeros(128, dtype=np.int8)
    for i in range(128):
        acc = np.int64(qb1[i])
        for j in range(128):
            acc += np.int64(q_h0[j]) * np.int64(qw1[i, j])
        if acc <= 0:
            q_h1[i] = 0
        else:
            q_h1[i] = requantize_accum(acc, os_h0, sw1, os_h1)

    # ── Layer 2: 128→128 ──
    q_h2 = np.zeros(128, dtype=np.int8)
    for i in range(128):
        acc = np.int64(qb2[i])
        for j in range(128):
            acc += np.int64(q_h1[j]) * np.int64(qw2[i, j])
        if acc <= 0:
            q_h2[i] = 0
        else:
            q_h2[i] = requantize_accum(acc, os_h1, sw2, os_h2)

    # ── Layer 3: 128→21 (output, no ReLU) ──
    q_out = np.zeros(21, dtype=np.int8)
    for i in range(21):
        acc = np.int64(qb3[i])
        for j in range(128):
            acc += np.int64(q_h2[j]) * np.int64(qw3[i, j])
        q_out[i] = requantize_accum(acc, os_h2, sw3, os_q)

    return q_out.astype(np.float64)


# ═══════════════════════════════════════════════════════════════════
# Test states
# ═══════════════════════════════════════════════════════════════════


def generate_states(n=500, seed=42):
    np.random.seed(seed)
    states = []
    for _ in range(n):
        profile = np.random.choice(["center", "aggressive", "defensive", "random"])
        sx, sy = np.random.uniform(-1, 1), np.random.uniform(-1, 1)
        svx, svy = np.random.uniform(-1, 1), np.random.uniform(-1, 1)
        if profile == "center":
            ox, oy = np.random.uniform(-0.2, 0.2), np.random.uniform(-0.2, 0.2)
        elif profile == "aggressive":
            ox, oy = sx + np.random.uniform(-0.3, 0.3), sy + np.random.uniform(-0.3, 0.3)
        elif profile == "defensive":
            ox, oy = np.random.uniform(-1, 1), np.random.uniform(-1, 1)
        else:
            ox, oy = np.random.uniform(-1, 1), np.random.uniform(-1, 1)
        ox, oy = np.clip(ox, -1, 1), np.clip(oy, -1, 1)
        d = np.sqrt((sx - ox) ** 2 + (sy - oy) ** 2)
        states.append([sx, sy, svx, svy, ox, oy, d])
    return np.array(states, dtype=np.float32)


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None)
    ap.add_argument("--n-states", type=int, default=500)
    ap.add_argument("--threshold", type=float, default=0.05)
    ap.add_argument("--calib-size", type=int, default=500)
    ap.add_argument("--percentile", type=float, default=99.9)
    args = ap.parse_args()

    # ── Model ──
    model_path = args.model or os.path.join(_PROJ_ROOT, "models", "v10_bayesopt_dqn.pt")
    if not os.path.exists(model_path):
        alt = os.path.join(os.path.dirname(_PROJ_ROOT), "models", "v10_bayesopt_dqn.pt")
        if os.path.exists(alt):
            model_path = alt
        else:
            print("[ERROR] Model not found.")
            return 1

    print(f"[INFO] Model: {os.path.basename(model_path)}")
    model = load_model(model_path)
    n_layers = len([layer for layer in model.net.children() if isinstance(layer, torch.nn.Linear)])
    total_p = sum(p.numel() for p in model.parameters())
    print(f"[INFO] Architecture: 7->128->128->128->21 ({n_layers} Linear, {total_p} params)")

    # ── Extract weights ──
    f_weights = extract_weights(model)
    shapes = [(w.shape, b.shape) for w, b in f_weights]
    print(f"[INFO] Weight shapes: {shapes}")

    # ── Quantize ──
    q_weights = []
    w_scales = []
    for w, b in f_weights:
        qw, sw = quantize_symmetric(w)
        qb = np.clip(np.round(b / sw), -128, 127).astype(np.int8)
        q_weights.append((qw, qb))
        w_scales.append(sw)
    q_weights = tuple(q_weights)
    w_scales = tuple(w_scales)
    for i, s in enumerate(w_scales):
        print(f"[INFO]  fc{i} weight_scale={s:.6f}")

    # ── Calibrate ──
    calib = generate_states(args.calib_size, seed=123)
    out_scales = calibrate(model, calib, args.percentile)
    for k, v in out_scales.items():
        print(f"[INFO]  {k} out_scale={v:.6f} (range +-{v * 127:.3f})")

    # ── Test ──
    test = generate_states(args.n_states, seed=42)
    print(f"[INFO] Test states: {len(test)}")

    matches, q_corrs, mism = 0, [], []
    d_f32, d_q8 = np.zeros(21, int), np.zeros(21, int)

    for i, s in enumerate(test):
        with torch.no_grad():
            qf = model(torch.tensor(s).unsqueeze(0)).numpy().flatten()
        qi = int8_inference(s, q_weights, w_scales, out_scales)
        af, aq = int(np.argmax(qf)), int(np.argmax(qi))
        d_f32[af] += 1
        d_q8[aq] += 1
        if af == aq:
            matches += 1
        elif len(mism) < 20:
            mism.append(
                {
                    "idx": i,
                    "state": [round(v, 3) for v in s.tolist()],
                    "af": af,
                    "aq": aq,
                    "qf_top3": [round(v, 2) for v in qf[np.argsort(qf)[-3:]].tolist()],
                    "qi_top3": [round(v, 2) for v in qi[np.argsort(qi)[-3:]].tolist()],
                }
            )
        if np.std(qf) > 1e-6:
            c = np.corrcoef(qf, qi)[0, 1]
            if not np.isnan(c):
                q_corrs.append(c)

    # ── Report ──
    acc = matches / len(test)
    mr = 1 - acc
    ac = np.mean(q_corrs) if q_corrs else 0
    print(f"\n{'=' * 60}")
    print("INT8 QUANTIZATION ACCURACY (v4 — 4-layer)")
    print(f"{'=' * 60}")
    print(f"Test states:              {len(test)}")
    print(f"Action matches:           {matches}/{len(test)}")
    print(f"Action accuracy:          {acc * 100:.2f}%")
    print(f"Mismatch rate:            {mr * 100:.2f}%")
    print(f"Mean Q correlation:       {ac:.4f}")
    passed = mr <= args.threshold
    print(f"\n[{'PASS' if passed else 'FAIL'}] Threshold <= {args.threshold * 100:.1f}%")
    if mism:
        print(f"\nTop {min(5, len(mism))} mismatches:")
        for m in mism[:5]:
            print(f"  [{m['idx']}] f32->{m['af']}  q8->{m['aq']}")
            print(f"       f32 Q: {m['qf_top3']}  q8 Q: {m['qi_top3']}")

    dm = np.sum(d_f32 == d_q8)
    print(f"\nDist matches: {dm}/21")
    print(f"  f32: {d_f32.tolist()}")
    print(f"  q8:  {d_q8.tolist()}")

    # ── Save ──
    rp = os.path.join(_PROJ_ROOT, "reports", "int8_quant_v4.json")
    os.makedirs(os.path.dirname(rp), exist_ok=True)
    report = {
        "architecture": "7->128->128->128->21",
        "total_params": total_p,
        "n_test": len(test),
        "accuracy": float(acc),
        "mismatch_rate": float(mr),
        "avg_q_corr": float(ac),
        "passed": passed,
        "threshold": args.threshold,
        "quant": {
            "weight_scales": [float(s) for s in w_scales],
            "output_scales": {k: float(v) for k, v in out_scales.items()},
        },
        "mismatches": mism,
        "dist_f32": d_f32.tolist(),
        "dist_q8": d_q8.tolist(),
    }
    with open(rp, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n[INFO] Report: {rp}")
    return 0 if passed else 1


if __name__ == "__main__":
    exit(main())
