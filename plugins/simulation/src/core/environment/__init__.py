"""Environment module for BottleSumo.

Provides unified environment creation across backends:
  - lightweight: Pure Python physics simulation (CPU)
  - gazebo:    High-fidelity Gazebo simulation (GPU recommended)
  - hil:       Hardware-in-the-Loop with real STM32
  - virtual:   Virtual HIL bridge for closed-loop testing
"""

from core.environment.factory import (
    make_bottlesumo,
    make,
    create_env,
    Backend,
    discover_backends,
    get_available_backends,
)

__all__ = [
    "make_bottlesumo",
    "make",
    "create_env",
    "Backend",
    "discover_backends",
    "get_available_backends",
]
