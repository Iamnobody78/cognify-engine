#!/usr/bin/env python3
"""TASK-005a: Gazebo step-response calibrator for N20 300rpm physicalized model.

Measures the closed-loop velocity step response (0 -> 0.53 m/s) of the
physicalized 34mm-wheel model, repeated N_RUNS times, and writes
simulation/calibration/step_response_<timestamp>.json.

Output fields (calibration-only ground truth for TASK-005d):
  - rise_time_90%  [s]  time from cmd onset to 90% of target linear velocity
  - settling_time  [s]  time to stay within +/-5% of target for 0.5s
  - overshoot      [%]  max velocity overshoot above target
  - steady_v       [m/s] mean velocity in the last 1.0s window
  - v_lin/omega_z  [m/s, rad/s] raw time series (for Rerun overlay)

PM constraint: this file is the ONLY allowed basis for TASK-005d tuning.
Usage:
    ros2 run bottlesumo_description step_response_calibrator  (as installed)
    python3 scripts/step_response_calibrator.py --duration 6 --runs 10
"""
import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry

CMD_LIN = 0.53          # FW_MAX linear velocity (21-action table, m/s)
DEFAULT_DURATION = 6.0  # seconds per run (3s settle + 3s step window)
DEFAULT_RUNS = 10
SETTLE_BAND = 0.05      # +/-5% settling band
OUT_DIR = Path(__file__).resolve().parent.parent / "simulation" / "calibration"


class StepResponseCalibrator(Node):
    def __init__(self, target: float, duration: float, runs: int, ns: str = ""):
        super().__init__("step_response_calibrator")
        self.target = target
        self.duration = duration
        self.runs = runs
        # BottleSumo launch uses namespace /bottlesumo (diff_drive plugin).
        # Accept --ns to override (e.g. "" for bare topics in other setups).
        self._cmd_topic = f"{ns}/cmd_vel" if ns else "/cmd_vel"
        self._odom_topic = f"{ns}/odom" if ns else "/odom"
        self._cmd_pub = self.create_publisher(Twist, self._cmd_topic, 10)
        self._odom_sub = self.create_subscription(Odometry, self._odom_topic, self._on_odom, 10)
        self._v_samples: list[tuple[float, float, float]] = []  # (t_odom, v_lin, omega_z)
        self._t0_cmd: float | None = None
        self._results = []
        self._pending_timer = None
        self._step_timer = None
        self._step_cmd_timer = None  # 0.5s one-shot step-command timer (cancelled in _send_step)
        self.get_logger().info(
            f"[TASK-005a] step_response target={target} m/s runs={runs} duration={duration}s "
            f"topics: {self._cmd_topic} / {self._odom_topic}"
        )
        self._schedule_next()

    # ── lifecycle ──────────────────────────────────────────────────────────
    def _schedule_next(self):
        if len(self._results) >= self.runs:
            self._finish()
            return
        self.get_logger().info(f"[TASK-005a] run {len(self._results)+1}/{self.runs}: resting 2s")
        self._pending_timer = self.create_timer(2.0, self._start_step)

    def _start_step(self):
        self._pending_timer.cancel()
        self._v_samples.clear()
        # 0.5s at zero to anchor the baseline, then step to target
        zero = Twist()
        self._cmd_pub.publish(zero)
        self._t0_cmd = None  # set on first nonzero cmd echo
        self._step_cmd_timer = self.create_timer(0.5, self._send_step)  # one-shot: cancelled inside _send_step

    def _send_step(self):
        if self._step_cmd_timer is not None:
            self._step_cmd_timer.cancel()  # one-shot: do NOT re-fire every 0.5s
        self.get_logger().info(f"[TASK-005a] STEP: 0 -> {self.target} m/s")
        cmd = Twist()
        cmd.linear.x = self.target
        self._cmd_pub.publish(cmd)
        self._t0_cmd = self.get_clock().now()
        self._step_timer = self.create_timer(0.1, self._check_run_end)

    def _check_run_end(self):
        if self._t0_cmd is None:
            return
        elapsed = (self.get_clock().now() - self._t0_cmd).nanoseconds * 1e-9
        if elapsed >= self.duration:
            self._step_timer.cancel()
            self._analyze_run()
            self._schedule_next()

    # ── data ───────────────────────────────────────────────────────────────
    def _on_odom(self, msg: Odometry):
        # NOTE: use wall-clock (monotonic) for the sample axis. The run-end check
        # uses get_clock().now() (wall). Using msg.header.stamp (sim time) here
        # mixed axes: with low RTF (WSL software rendering, RTF~0.09) a 6s wall
        # run spans <1s sim, so the "last 1.0s" steady window covered the whole
        # run and biased steady_v low (0.319 vs true 0.525).
        t = time.monotonic()
        v = msg.twist.twist.linear.x
        w = msg.twist.twist.angular.z
        self._v_samples.append((t, v, w))

    def _analyze_run(self):
        if not self._v_samples:
            self.get_logger().warn("no odom samples collected; run discarded")
            return
        # Align to step onset: first sample where v > 10% target
        t_onset = None
        for t, v, _ in self._v_samples:
            if v > 0.1 * self.target:
                t_onset = t
                break
        if t_onset is None:
            self.get_logger().warn("no response detected; run discarded")
            return
        base_t = t_onset
        target = self.target
        # rise time: first sample >= 90% target
        rise_time = None
        for t, v, _ in self._v_samples:
            if t >= base_t and v >= 0.9 * target:
                rise_time = t - base_t
                break
        # settling: last sample before staying within band for 0.5s
        settling_time = None
        for i, (t, v, _) in enumerate(self._v_samples):
            if t < base_t:
                continue
            window = self._v_samples[i:]
            window_ok = all(
                abs(vv - target) <= SETTLE_BAND * target
                for tt, vv, _ in window if tt - t < 0.5
            )
            if window_ok:
                settling_time = t - base_t
                break
        # overshoot
        peak = max((v for _, v, _ in self._v_samples if _ >= base_t), default=0.0)
        overshoot = max(0.0, (peak - target) / target * 100.0)
        # steady state (last 1.0s)
        t_end = self._v_samples[-1][0]
        steady = [v for t, v, _ in self._v_samples if t >= t_end - 1.0]
        steady_v = sum(steady) / len(steady) if steady else 0.0

        run = {
            "run": len(self._results) + 1,
            "target_m_s": target,
            # NOTE: use `is not None` — rise_time can legitimately be 0.0 when
            # the first >10% sample is already >=90% (low odom rate ~5Hz).
            "rise_time_90_s": round(rise_time, 4) if rise_time is not None else None,
            "settling_time_s": round(settling_time, 4) if settling_time is not None else None,
            "overshoot_pct": round(overshoot, 2),
            "steady_v_m_s": round(steady_v, 4),
        }
        self._results.append(run)
        self.get_logger().info(f"[TASK-005a] run {run['run']}: {run}")

    def _finish(self):
        if not self._results:
            self.get_logger().error("no valid runs; no JSON written")
            rclpy.shutdown()
            return
        avg = lambda k: round(sum(r[k] for r in self._results if r[k] is not None) / len(self._results), 4)
        summary = {
            "task": "TASK-005a step_response calibration",
            "model": "N20 6V 300rpm / 34mm sim wheel / damping=0.001 friction=0.02",
            "command": {"linear_x_m_s": CMD_LIN},
            "n_runs": len(self._results),
            "rise_time_90_mean_s": avg("rise_time_90_s"),
            "settling_time_mean_s": avg("settling_time_s"),
            "overshoot_mean_pct": avg("overshoot_pct"),
            "steady_v_mean_m_s": avg("steady_v_m_s"),
            "runs": self._results,
            "tuning_basis": "TASK-005d MUST be derived from this file (PM constraint)",
            "generated": datetime.utcnow().isoformat() + "Z",
        }
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        out = OUT_DIR / f"step_response_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        out.write_text(json.dumps(summary, indent=2))
        self.get_logger().info(f"[TASK-005a] DONE -> {out}")
        # stop the robot
        self._cmd_pub.publish(Twist())
        rclpy.shutdown()


def main():
    rclpy.init()
    args = argparse.ArgumentParser()
    args.add_argument("--duration", type=float, default=DEFAULT_DURATION)
    args.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    args.add_argument("--ns", type=str, default="/bottlesumo",
                      help="ROS namespace (launch default /bottlesumo); '' for bare topics")
    a = args.parse_args()
    node = StepResponseCalibrator(CMD_LIN, a.duration, a.runs, ns=a.ns)
    rclpy.spin(node)


if __name__ == "__main__":
    main()
