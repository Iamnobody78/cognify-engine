"""
sensor_noise_wrapper.py — Gym-style observation noise wrapper for sim-to-real transfer.

Injects realistic sensor noise into BottleSumo environment observations during
training. The policy learns to be robust against:
  - ToF edge sensor noise (VL53L0X: ±3% of reading, 940nm IR)
  - Opponent distance noise (ToF at range, ±2–5cm)
  - Opponent angle noise (IR seeker, ±5–15° angular resolution)
  - Wheel encoder noise (±0.02–0.05 m/s quantization)

Usage:
    from bottlesumo_pi.simulation.sensor_noise_wrapper import SensorNoiseWrapper
    env = SensorNoiseWrapper(env, profile="realistic")
    obs = env.reset()
    obs, reward, done, info = env.step(action)
"""

from dataclasses import dataclass

import numpy as np


@dataclass
class NoiseProfile:
    """Per-sensor noise parameters for a specific hardware configuration."""

    # Edge sensor noise: additive Gaussian std as fraction of reading (0–1 range)
    edge_std: float = 0.03  # ±3% of sensor reading (VL53L0X spec)

    # Opponent distance noise: additive Gaussian in meters
    opponent_dist_std: float = 0.03  # ±3cm ToF noise at 1m range

    # Opponent angle noise: additive Gaussian in radians
    opponent_angle_std: float = 0.10  # ±0.1 rad ≈ ±5.7° (IR seeker)

    # Robot speed noise: additive Gaussian in m/s
    speed_std: float = 0.03  # ±3 cm/s encoder noise

    # Sensor dropout: probability of receiving a stale reading
    # When triggered, returns last valid observation (simulates I2C bus contention)
    dropout_prob: float = 0.01  # 1% dropout rate

    # Observation delay: number of steps to delay the observation by
    # 0 = real-time, 1 = 1-step delay (50ms at 20Hz)
    latency_steps: int = 0

    # Magnitude range: noise magnitude is sampled uniformly from [min * std, max * std]
    # This models variable lighting/reflectivity conditions
    noise_min_scale: float = 0.5  # best-case: half nominal noise
    noise_max_scale: float = 2.0  # worst-case: double nominal noise

    @classmethod
    def none(cls) -> "NoiseProfile":
        """Zero noise (clean sim, used for baseline evaluation)."""
        return cls(
            edge_std=0.0,
            opponent_dist_std=0.0,
            opponent_angle_std=0.0,
            speed_std=0.0,
            dropout_prob=0.0,
            latency_steps=0,
        )

    @classmethod
    def realistic(cls) -> "NoiseProfile":
        """Realistic noise for sim-to-real training (default)."""
        return cls()

    @classmethod
    def harsh(cls) -> "NoiseProfile":
        """Worst-case noise for robustness testing."""
        return cls(
            edge_std=0.06,
            opponent_dist_std=0.08,
            opponent_angle_std=0.20,  # ±11.5°
            speed_std=0.06,
            dropout_prob=0.05,
            latency_steps=1,
            noise_min_scale=0.8,
            noise_max_scale=3.0,
        )

    @classmethod
    def mild(cls) -> "NoiseProfile":
        """Mild noise for fine-tuning after realistic training."""
        return cls(
            edge_std=0.01,
            opponent_dist_std=0.01,
            opponent_angle_std=0.03,
            speed_std=0.01,
            dropout_prob=0.002,
        )


class SensorNoiseWrapper:
    """Observation noise wrapper compatible with BottleSumo lightweight env.

    Observation format (7-dim):
        [edge_front, edge_back, edge_left, edge_right,
         opponent_dist, opponent_angle, robot_speed]

    Noise injection per-channel:
        indices 0–3: edge sensors  → add Gaussian * edge_std
        index 4:    opponent_dist  → add Gaussian * opponent_dist_std (meters)
        index 5:    opponent_angle → add Gaussian * opponent_angle_std (radians)
        index 6:    robot_speed    → add Gaussian * speed_std (m/s)

    Features:
        - Variable noise magnitude (uniform within [min_scale, max_scale] × std)
        - Sensor dropout with last-valid fallback
        - Latency buffer (N-step observation delay)
        - Noise seed control for reproducibility
    """

    def __init__(
        self,
        env,
        profile: NoiseProfile = None,
        seed: int | None = None,
    ):
        self.env = env
        self.profile = profile or NoiseProfile.realistic()

        # Ensure env has reset/step interface
        assert hasattr(env, "reset"), "Wrapped env must have reset()"
        assert hasattr(env, "step"), "Wrapped env must have step()"

        # RNG for reproducible noise
        self.rng = np.random.RandomState(seed)

        # Last valid observation (for dropout fallback)
        self._last_valid: np.ndarray | None = None

        # Latency buffer (circular queue for delayed observations)
        self._latency_buffer: list = []
        self._latency_idx: int = 0

        # Stats tracking
        self.noise_injected: int = 0
        self.dropouts_triggered: int = 0

    def _sample_noise_scale(self) -> float:
        """Sample a noise magnitude multiplier uniformly in [min, max]."""
        return self.rng.uniform(
            self.profile.noise_min_scale,
            self.profile.noise_max_scale,
        )

    def _inject_noise(self, obs: np.ndarray) -> np.ndarray:
        """Inject realistic sensor noise into observation.

        Noise magnitude is sampled per-step from [min_scale, max_scale] × std,
        modeling variable environmental conditions (lighting, reflectivity).
        """
        noisy = obs.copy().astype(np.float64)
        scale = self._sample_noise_scale()

        # Edge sensors (0–1 range): additive Gaussian
        for i in range(4):
            noisy[i] += self.rng.normal(0, self.profile.edge_std * scale)

        # Opponent distance (meters): additive Gaussian in meters
        noisy[4] += self.rng.normal(0, self.profile.opponent_dist_std * scale)

        # Opponent angle (radians): additive Gaussian
        noisy[5] += self.rng.normal(0, self.profile.opponent_angle_std * scale)

        # Robot speed (m/s): additive Gaussian
        noisy[6] += self.rng.normal(0, self.profile.speed_std * scale)

        # Clip edge sensors to valid range (prevent negative distances)
        for i in range(4):
            noisy[i] = np.clip(noisy[i], 0.0, 1.0)

        self.noise_injected += 1
        return noisy.astype(np.float32)

    def _apply_dropout(self, noisy: np.ndarray) -> np.ndarray:
        """Simulate sensor dropout by returning last valid observation."""
        if self.profile.dropout_prob > 0 and self.rng.random() < self.profile.dropout_prob:
            self.dropouts_triggered += 1
            if self._last_valid is not None:
                return self._last_valid.copy()
            return np.zeros_like(noisy)  # cold start: return zeros
        return noisy

    def _push_latency(self, obs: np.ndarray) -> np.ndarray:
        """Apply N-step observation delay via circular buffer."""
        max_steps = self.profile.latency_steps
        if max_steps <= 0:
            return obs

        # Initialize buffer if needed
        if len(self._latency_buffer) <= max_steps:
            self._latency_buffer = [obs.copy()] * (max_steps + 1)
            self._latency_idx = 0
            return obs

        # Write current, return oldest
        self._latency_buffer[self._latency_idx] = obs
        self._latency_idx = (self._latency_idx + 1) % (max_steps + 1)
        return self._latency_buffer[self._latency_idx].copy()

    def reset(self) -> tuple[np.ndarray, dict]:
        """Reset environment and apply noise to initial observation."""
        result = self.env.reset()
        if isinstance(result, tuple):
            obs, info = result
        else:
            obs, info = result, {}
        self._last_valid = np.asarray(obs, dtype=np.float32).copy()
        self._latency_buffer = []
        self._latency_idx = 0
        return self.step_observation(obs), info

    def step(self, action) -> tuple[np.ndarray, float, bool, bool, dict]:
        """Step environment and apply noise to observation."""
        result = self.env.step(action)
        # Handle both 4-tuple (obs, reward, done, info) and 5-tuple (obs, reward, done, truncated, info)
        if len(result) == 5:
            next_obs, reward, done, truncated, info = result
        else:
            next_obs, reward, done, info = result
            truncated = False
        self._last_valid = np.asarray(next_obs, dtype=np.float32).copy()
        noisy_obs = self.step_observation(next_obs)
        return noisy_obs, reward, done, truncated, info

    def step_observation(self, obs: np.ndarray) -> np.ndarray:
        """Full noise pipeline: inject → dropout → latency."""
        noisy = self._inject_noise(obs)
        noisy = self._apply_dropout(noisy)
        noisy = self._push_latency(noisy)
        return noisy

    def get_stats(self) -> dict:
        """Return noise injection statistics."""
        return {
            "noise_injected": self.noise_injected,
            "dropouts_triggered": self.dropouts_triggered,
            "dropout_rate": (self.dropouts_triggered / max(self.noise_injected, 1)),
        }

    # Delegate environment attributes to wrapped env
    def __getattr__(self, name):
        return getattr(self.env, name)


# ── Convenience functions ──────────────────────────────────────────


def wrap_env(env, profile_name: str = "realistic", seed: int | None = None):
    """Factory: wrap an environment with a named noise profile.

    Args:
        env: BottleSumo environment instance
        profile_name: "realistic" | "harsh" | "mild" | "none"
        seed: RNG seed for reproducibility

    Returns:
        SensorNoiseWrapper instance
    """
    profiles = {
        "realistic": NoiseProfile.realistic(),
        "harsh": NoiseProfile.harsh(),
        "mild": NoiseProfile.mild(),
        "none": NoiseProfile.none(),
    }
    if profile_name not in profiles:
        raise ValueError(f"Unknown profile '{profile_name}'. Options: {list(profiles.keys())}")
    return SensorNoiseWrapper(env, profile=profiles[profile_name], seed=seed)
