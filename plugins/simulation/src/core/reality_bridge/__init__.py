"""RealityBridge: P1 external world feedback alignment.

Standardized data interface between meta-theory and real-world signals.
4 input channels -> unified RealitySample -> meta-governance queries.

Channels:
  1. Simulation adapter (lightweight env / Gazebo state)
  2. Training log adapter (DQN loss, winrate, reward curves)
  3. User feedback adapter (human annotations as soft constraints)
  4. Shadow loop adapter (rule evolution + gate decision history)
"""

from .bridge import RealityBridge
from .models import (
    RealitySample,
    FeedbackSample,
    GapReport,
    Channel,
)

__all__ = [
    "RealityBridge",
    "RealitySample",
    "FeedbackSample",
    "GapReport",
    "Channel",
]
