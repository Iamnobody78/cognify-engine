"""
sensors.py — Sensor fusion & noise models for BottleSumo embedded deployment.

Provides:
- KalmanFilter1D: 1D Kalman for edge distance estimation
- ComplementaryFilter: IMU + edge sensor fusion
- SensorNoise: configurable noise models for sim-to-real transfer

Architectural position: common/sensors.py → used by lightweight_env.py for
realistic sim, and exported to firmware for STM32 deployment.
"""

from dataclasses import dataclass

import numpy as np


@dataclass
class KalmanFilter1D:
    """1-Dimensional Kalman filter for edge distance estimation.

    Architecture position: Replace raw edge sensor readings with filtered estimates.
    On STM32 this maps to ~200 bytes RAM, <1ms per update at 72MHz.

    Theory: X_k = X_{k-1} + K_k * (Z_k - X_{k-1})  with adaptive R based on confidence.
    """

    process_noise: float = 0.01  # Q: process noise (how much state drifts)
    measurement_noise: float = 0.1  # R: measurement noise (sensor inaccuracy)
    estimation_error: float = 1.0  # P: initial estimation error
    state: float = 0.0  # x: current filtered value

    def update(self, measurement: float) -> float:
        """Update filter with new measurement, return filtered estimate."""
        # Prediction: P = P + Q
        self.estimation_error += self.process_noise

        # Kalman gain: K = P / (P + R)
        kalman_gain = self.estimation_error / (self.estimation_error + self.measurement_noise)

        # Correction: x = x + K*(z - x), P = (1-K)*P
        self.state += kalman_gain * (measurement - self.state)
        self.estimation_error *= 1.0 - kalman_gain

        return self.state

    def reset(self) -> None:
        """Reset filter state."""
        self.estimation_error = 1.0
        self.state = 0.0


class MultiEdgeKalman:
    """Four Kalman filters for front/back/left/right edge sensors.

    Architecture position: Wraps raw edge_sensors array from environment,
    outputs filtered distances. Integrates into lightweight_env.py's step().
    """

    def __init__(self, process_noise: float = 0.01, measurement_noise: float = 0.1):
        self.filters = [
            KalmanFilter1D(process_noise, measurement_noise),
            KalmanFilter1D(process_noise, measurement_noise),
            KalmanFilter1D(process_noise, measurement_noise),
            KalmanFilter1D(process_noise, measurement_noise),
        ]

    def filter(self, raw_sensors: np.ndarray) -> np.ndarray:
        """Apply Kalman filter to 4-element edge sensor array."""
        filtered = np.zeros(4, dtype=np.float32)
        for i, (sensor, kf) in enumerate(zip(raw_sensors, self.filters, strict=False)):
            filtered[i] = kf.update(float(sensor))
        return filtered

    def reset(self) -> None:
        for kf in self.filters:
            kf.reset()


class ComplementaryFilter:
    """IMU + edge sensor complementary filter for heading estimation.

    Architecture position: Combines gyro (high-pass) + edge sensor orientation (low-pass).
    On STM32: <50 bytes RAM, <0.5ms at 72MHz.

    Theory: θ = α*(θ_{k-1} + ω*dt) + (1-α)*θ_edge
    where θ_edge is inferred from differential edge readings.
    """

    def __init__(self, alpha: float = 0.98):
        self.alpha = alpha  # gyro weight (typically 0.95-0.98)
        self.angle = 0.0  # current fused angle (radians)

    def update(self, gyro_rate: float, accel_angle: float, dt: float) -> float:
        """Fuse gyro rate and accelerometer-derived angle.

        Args:
            gyro_rate: angular velocity from gyro (rad/s)
            accel_angle: angle estimated from edge sensors or accelerometer (rad)
            dt: time step (seconds)
        """
        gyro_angle = self.angle + gyro_rate * dt
        self.angle = self.alpha * gyro_angle + (1.0 - self.alpha) * accel_angle
        return self.angle

    def edge_to_angle(self, front: float, back: float, left: float, right: float) -> float:
        """Infer robot heading relative to ring center from edge distances.

        Returns angle in radians. Positive = pointing right-of-center.
        """
        # Differential: which direction has more space?
        if (left + right) < 0.01:
            return 0.0
        lateral_bias = (right - left) / (left + right + 1e-6)
        return np.arctan(lateral_bias * 0.5)  # scale to rad

    def reset(self) -> None:
        self.angle = 0.0


@dataclass
class SensorNoise:
    """Configurable sensor noise model for sim-to-real transfer.

    Architecture position: Inject realistic noise into env observations.
    Enables training robust policies that survive sensor imperfections.
    """

    edge_std: float = 0.02  # std of Gaussian noise on edge sensors (normalized)
    opponent_x_std: float = 0.05  # opponent position uncertainty
    opponent_y_std: float = 0.05
    dropout_prob: float = 0.0  # probability of sensor dropout (NaN → use last valid)
    latency_steps: int = 0  # observation delay in steps

    def apply(self, obs: np.ndarray, last_valid: np.ndarray | None = None) -> np.ndarray:
        """Apply noise to observation vector.

        obs: [robot_x, robot_y, opponent_x, opponent_y, edge_f, edge_b, edge_l]
        """
        noisy = obs.copy()

        # Gaussian noise on edge sensors (indices 4-6)
        for i in [4, 5, 6]:
            noisy[i] += np.random.normal(0, self.edge_std)

        # Opponent position noise (indices 2-3)
        noisy[2] += np.random.normal(0, self.opponent_x_std)
        noisy[3] += np.random.normal(0, self.opponent_y_std)

        # Sensor dropout
        if self.dropout_prob > 0 and np.random.random() < self.dropout_prob:
            if last_valid is not None:
                noisy = last_valid.copy()
            else:
                noisy[:] = 0.0

        return np.clip(noisy, -1.0, 2.0)

    def to_firmware_struct(self) -> str:
        """Generate C struct for STM32 deployment."""
        return f"""typedef struct {{
    float edge_std;          // {self.edge_std}f
    float opponent_x_std;    // {self.opponent_x_std}f
    float opponent_y_std;    // {self.opponent_y_std}f
    float dropout_prob;      // {self.dropout_prob}f
    uint8_t latency_steps;   // {self.latency_steps}
}} SensorNoiseConfig;"""
