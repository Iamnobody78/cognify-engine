"""S60: evaluate distilled student (NanoQNet9) via v9 gate + latency benchmark.

Gate: v9_gate_evaluator --policy nano --model models/nano_s60_quick.pt (10 eps)
Latency: heuristic rule chain vs MLP forward (median of 1000).
"""
import sys, time, statistics
sys.path.insert(0, ".")

import torch
import numpy as np

from simulation.v9_gate_evaluator import V9GateEvaluator, V9RuleAgent, format_ci
from simulation.training.distill_chase_s44 import NanoQNet9


def load_nano(path):
    sd = torch.load(path, map_location="cpu", weights_only=True)
    hid = sd["net.0.weight"].shape[0]
    m = NanoQNet9(hidden_dim=hid, n_hidden=2)
    m.load_state_dict(sd)
    m.eval()
    return m


def bench_latency(teacher, student, obs, iters=1000):
    x = torch.FloatTensor(np.asarray(obs, dtype=np.float32)).unsqueeze(0)
    with torch.no_grad():
        # warmup
        for _ in range(50):
            teacher.select_action(obs)
            student(x)
        t0 = time.perf_counter()
        for _ in range(iters):
            teacher.select_action(obs)
        t_h = (time.perf_counter() - t0) / iters
        t0 = time.perf_counter()
        for _ in range(iters):
            student(x)
        t_m = (time.perf_counter() - t0) / iters
    n_params = sum(p.numel() for p in student.parameters())
    return t_h, t_m, n_params


def main():
    model_path = sys.argv[1] if len(sys.argv) > 1 else "models/nano_s60_quick.pt"

    # 1. gate — S45 接入点: --agent rl --model <path> (走 _RLGateAgent, 自适应 NanoQNet9 加载)
    ev = V9GateEvaluator(episodes=10, backend="lightweight", rl_model_path=model_path)
    rep = ev.evaluate(agent_name="rl")
    print("=== nano student GATE (10 eps) ===")
    print(format_ci(rep))
    for sn, sr in rep["per_strategy"].items():
        print(f"  {sn:12s} {sr['wins']}/{sr['total']}  WR={sr['winrate']:.1%}  avg_steps={sr['avg_steps']:.0f}")

    # 2. latency
    teacher = V9RuleAgent(force_heuristic=True)
    student = load_nano(model_path)
    obs = [0.55, 0.55, 0.55, 0.55, 0.42, 0.05, 0.1, 0.2, -0.1]
    t_h, t_m, n_params = bench_latency(teacher, student, obs)
    print(f"\n=== LATENCY ===")
    print(f"  heuristic: {t_h*1e6:.1f}us   MLP: {t_m*1e6:.1f}us   speedup={t_h/t_m:.1f}x   params={n_params}")


if __name__ == "__main__":
    main()
