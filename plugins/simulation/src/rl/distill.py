#!/usr/bin/env python3
"""
rl/distill.py — BottleSumo knowledge distillation entry point.

V3 opponent-aware distillation with paired Q-difference matching.
Distills a teacher DQN (128-neuron hidden) into a nano student (16-neuron)
suitable for real-time MCU inference.

Usage:
    python -m rl.distill                           # use default teacher
    python -m rl.distill --teacher path/to/model.pt

Architecture:
    rl/distill.py  →  simulation/training/distill_nano_v3.py
    (blueprint path)    (actual implementation: paired Q-diff matching)
"""

import argparse
import os
import sys

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

# Delegate to the V3 distill implementation
from simulation.training.distill_nano_v3 import distill_nano_v3

MODEL_DIR = os.path.join(_PROJ_ROOT, "models")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BottleSumo V3 distillation")
    parser.add_argument(
        "--teacher", type=str, default=None,
        help="Path to teacher model checkpoint",
    )
    args = parser.parse_args()

    teacher = args.teacher
    if not teacher:
        for candidate in ["v10_bayesopt_dqn.pt", "v10_dqn_best.pt"]:
            path = os.path.join(MODEL_DIR, candidate)
            if os.path.exists(path):
                teacher = path
                break

    if not teacher:
        print("ERROR: No teacher model found. Provide --teacher path/to/model.pt")
        sys.exit(1)

    print(f"Teacher: {teacher}")
    distill_nano_v3(teacher)
