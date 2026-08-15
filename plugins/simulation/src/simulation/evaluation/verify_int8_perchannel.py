"""
verify_int8_perchannel.py — Per-channel INT8 quantization test (v5)

Tests whether per-channel output quantization can rescue the
4-layer 128-wide network from post-training quantization collapse.
"""

import os
import sys

import numpy as np
import torch

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)
from bottlesumo_pi.common.network import DQN  # noqa: E402


def load_model(path):
    model = DQN(obs_dim=7, action_dim=21, hidden_dim=128, n_hidden=2)
    model.load_state_dict(torch.load(path, map_location="cpu", weights_only=False))
    model.eval()
    return model


def quantize_symmetric(t):
    mx = float(max(np.max(np.abs(t)), 1e-8))
    s = mx / 127.0
    return np.clip(np.round(t / s), -128, 127).astype(np.int8), np.float64(s)


def quantize_per_channel(t, axis=0):
    """Per-channel quantization: each output channel gets its own scale."""
    mx = np.max(np.abs(t), axis=1, keepdims=True)  # per-row or per-output
    mx = np.maximum(mx, 1e-8)
    s = mx / 127.0
    q = np.clip(np.round(t / s), -128, 127).astype(np.int8)
    return q, s.flatten().astype(np.float64)


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


def per_channel_forward(state_f32, q_weights_perch, w_scales_perch, calib_out_scales):
    """INT8 inference with per-channel quantization on weights."""

    # Unpack: each layer has per-output-channel weight scales
    (qw0, qb0, sw0_ch), (qw1, qb1, sw1_ch), (qw2, qb2, sw2_ch), (qw3, qb3, sw3_ch) = q_weights_perch
    os0, os1, os2, os_q = calib_out_scales  # per-layer output scales (from calibration)

    # Input quant
    in_max = max(float(np.max(np.abs(state_f32))), 0.01)
    in_scale = in_max / 127.0
    q_in = np.clip(np.round(state_f32 / in_scale), -128, 127).astype(np.int8)

    def requant_ch(acc, in_s, w_s_ch, out_s_ch):
        """Requantize with per-channel scales."""
        rf = (in_s * w_s_ch) / out_s_ch
        if rf < 1e-30:
            return np.int8(0)
        r, n = float(rf), np.int32(0)
        while r >= 1.0:
            r *= 0.5
            n += 1
        while r < 0.5:
            r *= 2.0
            n -= 1
        mult = max(np.int64(round(r * 2147483648.0)), np.int64(1))
        val = (np.int64(acc) * mult) >> (31 - int(n))
        return np.int8(np.clip(val, -128, 127))

    # Layer 0: 7->128, per-channel
    q_h0 = np.zeros(128, dtype=np.int8)
    for i in range(128):
        acc = np.int64(qb0[i])
        for j in range(7):
            acc += np.int64(q_in[j]) * np.int64(qw0[i, j])
        if acc <= 0:
            q_h0[i] = 0
        else:
            q_h0[i] = requant_ch(acc, in_scale, sw0_ch[i], os0[i])

    # Layer 1: 128->128, per-channel
    q_h1 = np.zeros(128, dtype=np.int8)
    for i in range(128):
        acc = np.int64(qb1[i])
        for j in range(128):
            acc += np.int64(q_h0[j]) * np.int64(qw1[i, j])
        if acc <= 0:
            q_h1[i] = 0
        else:
            q_h1[i] = requant_ch(acc, os0[i], sw1_ch[i], os1[i])

    # Layer 2: 128->128, per-channel
    q_h2 = np.zeros(128, dtype=np.int8)
    for i in range(128):
        acc = np.int64(qb2[i])
        for j in range(128):
            acc += np.int64(q_h1[j]) * np.int64(qw2[i, j])
        if acc <= 0:
            q_h2[i] = 0
        else:
            q_h2[i] = requant_ch(acc, os1[i], sw2_ch[i], os2[i])

    # Layer 3: 128->21, per-channel
    q_out = np.zeros(21, dtype=np.int8)
    for i in range(21):
        acc = np.int64(qb3[i])
        for j in range(128):
            acc += np.int64(q_h2[j]) * np.int64(qw3[i, j])
        q_out[i] = requant_ch(acc, os2[i % 128], sw3_ch[i], os_q[i])

    return q_out.astype(np.float64)


def main():
    model = load_model(os.path.join(os.path.dirname(_PROJ_ROOT), "models", "v10_bayesopt_dqn.pt"))

    # Extract weights
    layers = [layer for layer in model.net.children() if isinstance(layer, torch.nn.Linear)]
    f_weights = [(lyr.weight.detach().numpy(), lyr.bias.detach().numpy()) for lyr in layers]

    # Per-channel quantization of weights
    q_weights_perch = []
    w_scales_perch = []
    for w, b in f_weights:
        qw, ws_ch = quantize_per_channel(w)
        # Bias scale = weight_scale for each channel
        qb = np.clip(np.round(b / ws_ch), -128, 127).astype(np.int8)
        q_weights_perch.append((qw, qb, ws_ch))
        w_scales_perch.append(ws_ch)

    print("Per-channel weight scales:")
    for i, ws in enumerate(w_scales_perch):
        print(f"  fc{i}: {ws[:6]}... range [{ws.min():.6f}, {ws.max():.6f}]")

    # Calibrate per-channel output scales
    calib = generate_states(500, seed=123)
    # Run float32 forward to get per-channel output magnitudes
    x = torch.tensor(calib, dtype=torch.float32)
    with torch.no_grad():
        h0 = np.maximum(layers[0](x).numpy(), 0)
        h1 = np.maximum(layers[1](torch.tensor(h0)).numpy(), 0)
        h2 = np.maximum(layers[2](torch.tensor(h1)).numpy(), 0)
        qv = layers[3](torch.tensor(h2)).numpy()

    # Per-channel output scales (max of each channel across batch)
    os0 = np.max(np.abs(h0), axis=0) / 127.0
    os1 = np.max(np.abs(h1), axis=0) / 127.0
    os2 = np.max(np.abs(h2), axis=0) / 127.0
    os_q = np.max(np.abs(qv), axis=0) / 127.0

    # Clamp to avoid zero
    os0 = np.maximum(os0, 1e-6)
    os1 = np.maximum(os1, 1e-6)
    os2 = np.maximum(os2, 1e-6)
    os_q = np.maximum(os_q, 1e-6)

    out_scales_ch = (os0, os1, os2, os_q)

    print("\nPer-channel output scales:")
    for _i, (name, osc) in enumerate([("h0", os0), ("h1", os1), ("h2", os2), ("q", os_q)]):
        print(f"  {name}: {osc[:6]}... range [{osc.min():.6f}, {osc.max():.6f}]")

    # Test
    test = generate_states(500, seed=42)
    matches, mism = 0, []
    d_f32, d_q8 = np.zeros(21, int), np.zeros(21, int)

    for i, s in enumerate(test):
        with torch.no_grad():
            qf = model(torch.tensor(s).unsqueeze(0)).numpy().flatten()
        qi = per_channel_forward(s, q_weights_perch, w_scales_perch, out_scales_ch)
        af, aq = int(np.argmax(qf)), int(np.argmax(qi))
        d_f32[af] += 1
        d_q8[aq] += 1
        if af == aq:
            matches += 1
        elif len(mism) < 10:
            mism.append(
                {
                    "idx": i,
                    "af": af,
                    "aq": aq,
                    "qf_top3": [round(v, 2) for v in qf[np.argsort(qf)[-3:]].tolist()],
                    "qi_top3": [round(v, 2) for v in qi[np.argsort(qi)[-3:]].tolist()],
                }
            )

    acc = matches / len(test)
    print(f"\n{'=' * 60}")
    print("PER-CHANNEL INT8 ACCURACY")
    print(f"{'=' * 60}")
    print(f"Action matches: {matches}/{len(test)}")
    print(f"Accuracy:       {acc * 100:.2f}%")
    print(f"Mismatch rate:  {(1 - acc) * 100:.2f}%")
    print(f"Dist f32: {d_f32.tolist()}")
    print(f"Dist q8:  {d_q8.tolist()}")

    if mism:
        print("\nFirst mismatches:")
        for m in mism[:5]:
            print(
                f"  [{m['idx']}] f32->{m['af']} q8->{m['aq']} | f32:{m['qf_top3']} q8:{m['qi_top3']}"
            )


if __name__ == "__main__":
    main()
