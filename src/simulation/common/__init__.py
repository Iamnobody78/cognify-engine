"""
BottleSumo Common Module — shared RL infrastructure.

Consolidates duplicated code from train_*.py, eval_*.py, distill_nano.py, gatekeeper.py.
Usage:
    from bottlesumo_pi.common import DQN, DQNAgent, ReplayBuffer, evaluate, Config
"""

from .agent import DQNAgent
from .config import Config
from .evaluation import evaluate
from .network import DQN, NanoQNet
from .offline import CQLLoss, TrajectoryDataset, behavior_cloning_pretrain
from .replay_buffer import ReplayBuffer
from .sensors import ComplementaryFilter, KalmanFilter1D, MultiEdgeKalman, SensorNoise

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
]
