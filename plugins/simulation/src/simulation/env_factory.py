"""
env_factory.py — Unified BottleSumo Environment Factory (DEBT D-002)

Unified factory pattern: make("bottlesumo", backend="lightweight|gazebo").

- lightweight: LightweightBottleSumoEnv (2D fast sim, DQN/DAgger/IRL loop)
- gazebo:      bottlesumo_gym (Gazebo/ROS2 3D sim) — optional; raises informative
               ImportError if the backend package is not installed.

Usage:
    from simulation.env_factory import make
    env = make("bottlesumo", backend="lightweight", opponent_profile="aggressive")

Ablation tests across sim backends become: same factory call, different backend.
"""

from __future__ import annotations

import importlib
from typing import Any, Dict, List, Optional

BACKENDS: Dict[str, Dict[str, Any]] = {
    "bottlesumo": {
        "lightweight": ("simulation.lightweight_env", "LightweightBottleSumoEnv"),
        "gazebo": ("bottlesumo_gym", "BottleSumoGazeboEnv"),
    },
}

# Known package names checked for informative error messages.
_GAZEBO_PKG_HINTS = (
    "bottlesumo_gym",
    "gazebo_msgs",
    "rclpy",
)


def list_backends(env_name: str = "bottlesumo") -> List[str]:
    """Return backend names registered for the given environment."""
    entry = BACKENDS.get(env_name)
    if entry is None:
        return []
    return list(entry.keys())


def _resolve(env_name: str, backend: str) -> tuple:
    entry = BACKENDS.get(env_name)
    if entry is None:
        raise ValueError(
            f"Unknown environment {env_name!r}. Known: {sorted(BACKENDS)}"
        )
    spec = entry.get(backend)
    if spec is None:
        raise ValueError(
            f"Unknown backend {backend!r} for env {env_name!r}. "
            f"Known backends: {list(entry.keys())}"
        )
    return spec


def make(env_name: str = "bottlesumo", backend: str = "lightweight", **kwargs) -> Any:
    """
    Instantiate a BottleSumo environment by backend name.

    Raises:
        ValueError:   unknown env/backend name
        ImportError:  backend package missing (e.g. gazebo without bottlesumo_gym)
    """
    module_path, class_name = _resolve(env_name, backend)
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:  # pragma: no cover - depends on env
        raise ImportError(
            f"Backend {backend!r} for {env_name!r} requires package "
            f"{module_path!r} which could not be imported ({exc}). "
            f"Hints: lightweight is always available; gazebo requires "
            f"ROS2 + bottlesumo_gym (see DEBT D-002 / Phase C install)."
        ) from exc
    cls = getattr(module, class_name)
    return cls(**kwargs)


def make_lightweight(**kwargs) -> Any:
    """Convenience: lightweight backend with default name."""
    return make("bottlesumo", backend="lightweight", **kwargs)
