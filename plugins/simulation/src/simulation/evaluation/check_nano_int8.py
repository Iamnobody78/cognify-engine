"""Quick INT8 accuracy test for Nano model (7→16→16→21, 757 params)."""

import os
import sys

import numpy as np
import torch

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_WS_ROOT = os.path.dirname(_PROJ_ROOT)
if _WS_ROOT not in sys.path:
    sys.path.insert(0, _WS_ROOT)
# bottlesumo_pi import needs WS_ROOT in path
sys.path.insert(0, _WS_ROOT)
from bottlesumo_pi.common.export_c import _extract_linear_layers  # noqa: E402
from bottlesumo_pi.common.network import DQN  # noqa: E402

os.chdir(_WS_ROOT)
ckpt = torch.load("models/nano_student.pt", map_location="cpu", weights_only=False)
sd = ckpt["state_dict"]
layers = _extract_linear_layers(sd)
(_, w0, b0), (_, w1, b1), (_, w2, b2) = layers

model = DQN(obs_dim=7, action_dim=21, hidden_dim=16, n_hidden=1)
model.load_state_dict(sd)
model.eval()

# Quantize
s0 = max(abs(w0).max(), 1e-8) / 127.0
qw0 = np.clip(np.round(w0 / s0), -128, 127).astype(np.int8)
sb0 = s0
qb0 = np.clip(np.round(b0 / sb0), -128, 127).astype(np.int8)
s1 = max(abs(w1).max(), 1e-8) / 127.0
qw1 = np.clip(np.round(w1 / s1), -128, 127).astype(np.int8)
sb1 = s1
qb1 = np.clip(np.round(b1 / sb1), -128, 127).astype(np.int8)
s2 = max(abs(w2).max(), 1e-8) / 127.0
qw2 = np.clip(np.round(w2 / s2), -128, 127).astype(np.int8)
sb2 = s2
qb2 = np.clip(np.round(b2 / sb2), -128, 127).astype(np.int8)

# Test states
np.random.seed(42)
n_test = 200
states = np.random.uniform(-1, 1, (n_test, 7)).astype(np.float32)

# Float32 batch
with torch.no_grad():
    qf_all = model(torch.tensor(states)).numpy()  # (200, 21)

# INT8 batch inference (vectorized with numpy)
in_scales = np.maximum(np.abs(states).max(axis=1), 0.01) / 127.0
q_in = np.clip(np.round(states / in_scales[:, None]), -128, 127).astype(np.int32)

# All matmul in int64 to avoid overflow
q_in64 = q_in.astype(np.int64)
qw0_64 = qw0.astype(np.int64)
qw1_64 = qw1.astype(np.int64)
qw2_64 = qw2.astype(np.int64)
qb0_64 = qb0.astype(np.int64)
qb1_64 = qb1.astype(np.int64)
qb2_64 = qb2.astype(np.int64)

# L0: (200,16) = relu(q_in @ qw0.T + qb0)
h0 = np.maximum(q_in64 @ qw0_64.T + qb0_64, 0)

# L1: (200,16)
h1 = np.maximum(h0 @ qw1_64.T + qb1_64, 0)

# L2: (200,21)
out_int = h1 @ qw2_64.T + qb2_64

# Effective scale per sample
eff_scales = in_scales * s0 * s1 * s2
qi_all = out_int.astype(np.float64) * eff_scales[:, None]

# Compare
af = np.argmax(qf_all, axis=1)
ai = np.argmax(qi_all, axis=1)
matches = np.sum(af == ai)
acc = matches / n_test
corr = np.corrcoef(qf_all.flatten(), qi_all.flatten())[0, 1]

print("Nano 7->16->16->21 INT8 vs Float32")
print(f"  Test states: {n_test}")
print(f"  Action matches: {matches}/{n_test}")
print(f"  Accuracy: {acc * 100:.1f}%")
print(f"  Q correlation: {corr:.4f}")

# Show mismatches
mism = np.where(af != ai)[0]
if len(mism) > 0:
    print("\n  First 5 mismatches:")
    for mi in mism[:5]:
        print(
            f"    [{mi}] f32->{af[mi]} q8->{ai[mi]} | f32 top3={qf_all[mi][np.argsort(qf_all[mi])[-3:]].round(2)} | q8 top3={qi_all[mi][np.argsort(qi_all[mi])[-3:]].round(2)}"
        )

# Compare with V10
ckpt_v10 = torch.load("models/v10_bayesopt_dqn.pt", map_location="cpu", weights_only=False)
v10 = DQN(obs_dim=7, action_dim=21, hidden_dim=128, n_hidden=2)
v10.load_state_dict(ckpt_v10)
v10.eval()
with torch.no_grad():
    qv = v10(torch.tensor(states)).numpy()
av = np.argmax(qv, axis=1)
nano_f32_matches = np.sum(af == av)
print(
    f"\n  V10 vs Nano (f32) agreement: {nano_f32_matches}/{n_test} = {nano_f32_matches / n_test * 100:.1f}%"
)
print(
    f"  V10 vs Nano INT8 agreement: {np.sum(av == ai)}/{n_test} = {np.sum(av == ai) / n_test * 100:.1f}%"
)
