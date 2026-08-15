#!/usr/bin/env python3
"""
rl/train.py — BottleSumo DQN training entry point.

This is the BLUEPRINT-ALIGNED entry point for DQN reinforcement learning
training. It delegates to simulation/training/train.py while providing a
clean, self-documenting API at the rl/ module level.

Usage:
    python -m rl.train                    # default config
    python -m rl.train --config bayesopt  # bayesian-optimized hyperparams
    python -m rl.train --config nano      # nano student config
    python -m rl.train --config quick_test # CI smoke test

Architecture:
    rl/train.py  →  simulation/training/train.py  →  DQNAgent + LightweightEnv
    (blueprint path)    (actual implementation)
"""

import os
import sys

# Ensure bottlesumo_pi is on path regardless of invocation method
_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

# Delegate to the canonical implementation in simulation/
from simulation.training.train import main

if __name__ == "__main__":
    main()
