"""
BottleSumo RL Module — re-exports from common infrastructure + standalone submodules.

Blueprint v10.3 Layer 2 alignment:
    rl/train.py         — DQN training entry point
    rl/distill.py       — knowledge distillation entry point
    rl/causal/          — causal inference (SCM, CATE, CF-Net)

The core RL code lives in bottlesumo_pi/common/ (shared between training/simulation/HIL).
This module provides a clean import path matching the blueprint structure.

Usage:
    from bottlesumo_pi.rl import DQN, DQNAgent, ReplayBuffer, evaluate, Config
    from bottlesumo_pi.rl.causal import StructuralCausalModel, CATEstimator
"""

from bottlesumo_pi.common import (
    DQN,
    ComplementaryFilter,
    Config,
    CQLLoss,
    DQNAgent,
    KalmanFilter1D,
    MultiEdgeKalman,
    NanoQNet,
    ReplayBuffer,
    SensorNoise,
    TrajectoryDataset,
    behavior_cloning_pretrain,
    evaluate,
)

# Submodule entry points (blueprint-aligned standalone scripts)
from . import train
from . import distill
from . import causal

__all__ = [
    "DQN",
    "NanoQNet",
    "DQNAgent",
    "ReplayBuffer",
    "evaluate",
    "Config",
    "KalmanFilter1D",
    "MultiEdgeKalman",
    "ComplementaryFilter",
    "SensorNoise",
    "TrajectoryDataset",
    "behavior_cloning_pretrain",
    "CQLLoss",
    "train",
    "distill",
    "causal",
]
