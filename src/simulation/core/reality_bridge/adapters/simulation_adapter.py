"""Simulation adapter: bridges BottleSumo env -> RealitySample stream.

Supports:
  - LightweightBottleSumoEnv (bottlesumo_pi.simulation.lightweight_env)
  - ContinuousBottleSumoEnv (bottlesumo_pi.simulation.continuous_env)
  - Future: Gazebo ROS2 subscription
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from ..models import Channel, RealitySample


class SimulationAdapter:
    """Wraps a BottleSumo environment and emits RealitySamples on each step."""

    def __init__(self, env: Any, env_label: str = "lightweight"):
        """Wrap an existing BottleSumo environment.

        Args:
            env: A gym-like environment with step()/reset().
            env_label: Human-readable label for the environment variant.
        """
        self._env = env
        self._label = env_label
        self._episode_id = 0
        self._step = 0
        self._current_obs: Optional[List[float]] = None
        self._listeners: List[Callable[[RealitySample], None]] = []

    # ── Public API ──────────────────────────────────────────────────────

    def on_sample(self, callback: Callable[[RealitySample], None]) -> None:
        """Register a listener that receives every RealitySample emitted."""
        self._listeners.append(callback)

    def reset(self) -> List[float]:
        """Reset the environment and emit an initial sample."""
        self._episode_id += 1
        self._step = 0
        obs = self._env.reset()
        self._current_obs = self._to_list(obs)
        self._emit(reward=0.0, win=False)
        return obs

    def step(self, action: int) -> Dict[str, Any]:
        """Take a step and emit a RealitySample.

        Returns the standard gym tuple (obs, reward, done, info).
        """
        result = self._env.step(action)
        # Handle both (obs, reward, done, info) tuple and dict returns
        if isinstance(result, tuple) and len(result) >= 3:
            obs, reward, done = result[0], result[1], result[2]
            info = result[3] if len(result) > 3 else {}
        else:
            obs = result.get("obs", self._current_obs)
            reward = result.get("reward", 0.0)
            done = result.get("done", False)
            info = result

        self._step += 1
        self._current_obs = self._to_list(obs)

        win = bool(info.get("win", False)) if isinstance(info, dict) else False
        self._emit(reward=float(reward), win=win, action=action)

        return {"obs": obs, "reward": reward, "done": done, "info": info}

    # ── Utility ─────────────────────────────────────────────────────────

    def _to_list(self, obs: Any) -> Optional[List[float]]:
        """Convert observation to a flat list of floats."""
        if obs is None:
            return None
        if hasattr(obs, "tolist"):
            return [float(x) for x in obs.tolist()]
        if isinstance(obs, (list, tuple)):
            return [float(x) for x in obs]
        return [float(obs)]

    def _emit(self, reward: float = 0.0, win: bool = False,
              action: Optional[int] = None) -> None:
        """Create and broadcast a RealitySample."""
        sample = RealitySample(
            channel=Channel.SIMULATION,
            timestamp=time.time(),
            episode_id=self._episode_id,
            step=self._step,
            obs=self._current_obs,
            action=action,
            reward=reward,
            win=win,
            tags=[self._label],
        )

        for listener in self._listeners:
            try:
                listener(sample)
            except Exception:
                pass  # listeners must not break the simulation

    @property
    def episode_id(self) -> int:
        return self._episode_id

    @property
    def step_count(self) -> int:
        return self._step
