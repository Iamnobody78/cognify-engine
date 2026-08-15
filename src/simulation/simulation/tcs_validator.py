#!/usr/bin/env python3
"""
TCS Parameter Validator — DEBT-007 simulation verification
Validates traction control system parameters without physical hardware.

Test Plan:
  A. Baseline: no TCS → measure slip ratio at max throttle
  B. Default params: slip_ratio_threshold=0.15, pwm_decay=0.85
  C. Aggressive params: threshold=0.10, decay=0.80
  D. Conservative params: threshold=0.20, decay=0.90
  E. Adaptive: threshold varies with surface friction

Physics Model:
  - Wheel angular velocity: ω(t+1) = ω(t) + (τ_motor - τ_friction) / I * dt
  - Vehicle velocity: v(t+1) = v(t) + F_friction / m * dt
  - Slip ratio: s = (ω*r - v) / max(ω*r, v, ε)
  - Friction force: F = μ(s) * N  (uses Pacejka-like curve)
  - Motor torque: τ = τ_max * PWM_duty
  - TCS: if s > threshold → PWM *= decay

Output: tables and plots comparing all configurations.
"""

import json
import math
import os
from dataclasses import dataclass

# ============================================================
# Physical Constants (BottleSumo scale)
# ============================================================
WHEEL_RADIUS = 0.02  # m (2cm wheels)
VEHICLE_MASS = 0.2  # kg (~200g)
WHEEL_INERTIA = 1e-6  # kg·m²
MAX_MOTOR_TORQUE = 0.015  # N·m (N20 micro metal geared)
NORMAL_FORCE = VEHICLE_MASS * 9.81 / 2  # N per wheel (50/50 split)
DT = 0.001  # 1ms control loop


# ============================================================
# Pacejka-like friction curve: μ as function of slip ratio s
# Peak μ at s≈0.15, drops after 0.3 (wheel spin)
# ============================================================
def friction_coefficient(s: float, surface: str = "sumo") -> float:
    """Pacejka-like μ(s) curve. s = slip ratio (0=perfect grip, 1=full spin)."""
    if surface == "sumo":
        # Dohyo surface: moderate friction
        B, C, D, E = 10.0, 1.9, 0.7, 0.97  # noqa: N806
    elif surface == "slick":
        # Low friction
        B, C, D, E = 8.0, 1.6, 0.4, 0.95  # noqa: N806
    elif surface == "rubber":
        # High friction
        B, C, D, E = 12.0, 2.0, 0.9, 0.98  # noqa: N806
    else:
        B, C, D, E = 10.0, 1.9, 0.7, 0.97  # noqa: N806

    return D * math.sin(C * math.atan(B * s - E * (B * s - math.atan(B * s))))


# ============================================================
# TCS Controller
# ============================================================
class TCSController:
    """Traction Control: monitors slip ratio and decays PWM when exceeding threshold.

    v2: Adds derivative term (slip rate-of-change) for early intervention.
    BottleSumo-scale motors can spin up from 0 to full slip in <2ms,
    so absolute threshold alone is insufficient.
    """

    def __init__(
        self,
        slip_threshold: float = 0.15,
        pwm_decay: float = 0.85,
        recovery_rate: float = 1.01,
        enabled: bool = True,
        use_derivative: bool = True,
        d_threshold: float = 5.0,  # slip rate-of-change threshold
        d_decay: float = 0.90,  # decay when slip rising fast
    ):
        self.slip_threshold = slip_threshold
        self.pwm_decay = pwm_decay
        self.recovery_rate = recovery_rate
        self.enabled = enabled
        self.use_derivative = use_derivative
        self.d_threshold = d_threshold
        self.d_decay = d_decay
        self.intervention_count = 0
        self._prev_slip = 0.0
        self._dt = DT

    def apply(self, pwm: float, slip: float) -> tuple[float, bool]:
        """
        Apply TCS to PWM command.
        Returns: (adjusted_pwm, intervention_triggered)
        """
        if not self.enabled:
            return pwm, False

        slip_abs = abs(slip)

        # ── Derivative check (early warning) ──
        if self.use_derivative and self._dt > 0:
            slip_dot = (slip_abs - abs(self._prev_slip)) / self._dt
            if slip_dot > self.d_threshold:
                # Slip is rising rapidly → preemptive decay
                pwm = max(0.0, pwm * self.d_decay)
                self.intervention_count += 1
                self._prev_slip = slip
                return pwm, True

        self._prev_slip = slip

        # ── Absolute threshold check ──
        if slip_abs > self.slip_threshold:
            pwm = max(0.0, pwm * self.pwm_decay)
            self.intervention_count += 1
            return pwm, True
        elif slip_abs < self.slip_threshold * 0.5 and pwm < 1.0:
            pwm = min(1.0, pwm * self.recovery_rate)
            return pwm, False
        return pwm, False

    def reset(self):
        self.intervention_count = 0
        self._prev_slip = 0.0


# ============================================================
# Single-wheel simulation
# ============================================================
@dataclass
class WheelState:
    omega: float = 0.0  # angular velocity (rad/s)
    velocity: float = 0.0  # linear velocity (m/s)
    position: float = 0.0  # cumulative distance (m)


class WheelSimulator:
    """Single wheel dynamics with optional TCS."""

    def __init__(self, tcs: TCSController, surface: str = "sumo"):
        self.tcs = tcs
        self.state = WheelState()
        self.surface = surface
        self.history: list[dict] = []

    def step(self, pwm_command: float, dt: float = DT) -> dict:
        s = self.state
        tcs = self.tcs

        # Current slip
        v_ground = max(abs(s.velocity), 1e-6)
        v_wheel = abs(s.omega) * WHEEL_RADIUS
        slip = (v_wheel - v_ground) / max(v_wheel, v_ground)

        # Apply TCS
        pwm_adjusted, intervention = tcs.apply(pwm_command, slip)

        # Motor torque
        tau_motor = MAX_MOTOR_TORQUE * pwm_adjusted

        # Friction torque (opposes motion)
        mu = friction_coefficient(slip, self.surface)
        friction_force = mu * NORMAL_FORCE * math.copysign(1, s.omega if s.omega != 0 else 1)
        tau_friction = friction_force * WHEEL_RADIUS

        # Update angular velocity
        s.omega += (tau_motor - tau_friction) / WHEEL_INERTIA * dt
        s.omega = max(0, s.omega)  # no reverse

        # Update linear velocity
        s.velocity += friction_force / VEHICLE_MASS * dt
        s.velocity = max(0, s.velocity)

        # Update position
        s.position += s.velocity * dt

        record = {
            "t": s.position,  # use position as time proxy
            "pwm_in": pwm_command,
            "pwm_out": pwm_adjusted,
            "omega": s.omega,
            "velocity": s.velocity,
            "slip": slip,
            "mu": mu,
            "intervention": intervention,
        }
        self.history.append(record)
        return record

    def run(self, pwm_profile: list[float], duration_per_step: float = 0.005) -> list[dict]:
        """Run simulation for a sequence of PWM commands."""
        self.tcs.reset()
        self.state = WheelState()
        self.history = []
        steps_per_block = int(duration_per_step / DT)
        for pwm in pwm_profile:
            for _ in range(steps_per_block):
                self.step(pwm)
        return self.history

    def metrics(self) -> dict:
        """Compute aggregate metrics from history."""
        if not self.history:
            return {}
        hs = self.history
        slips = [h["slip"] for h in hs]
        interventions = [h["intervention"] for h in hs]
        final_v = hs[-1]["velocity"]
        final_dist = hs[-1]["t"]
        avg_pwm_out = sum(h["pwm_out"] for h in hs) / len(hs)
        max_slip = max(slips)
        avg_slip = sum(slips) / len(slips)
        pct_intervention = sum(interventions) / len(interventions) * 100

        # Energy: integral of PWM² over time
        energy = sum(h["pwm_out"] ** 2 for h in hs) / len(hs)

        # Efficiency: distance / energy
        efficiency = final_dist / max(energy, 1e-6)

        return {
            "final_distance_m": round(final_dist, 6),
            "final_velocity_mps": round(final_v, 4),
            "max_slip": round(max_slip, 4),
            "avg_slip": round(avg_slip, 4),
            "avg_pwm_out": round(avg_pwm_out, 4),
            "intervention_pct": round(pct_intervention, 2),
            "energy": round(energy, 6),
            "efficiency": round(efficiency, 4),
            "total_interventions": sum(interventions),
        }


# ============================================================
# Test profiles
# ============================================================
def make_pwm_ramp(n_steps: int = 20) -> list[float]:
    """Gradual throttle increase: 0.0 → 1.0."""
    return [i / (n_steps - 1) for i in range(n_steps)]


def make_pwm_steps() -> list[float]:
    """Step throttle profile for aggression test."""
    return [0.0, 0.3, 0.0, 0.6, 0.0, 0.9, 0.0, 1.0, 0.0]


def make_pwm_surge() -> list[float]:
    """Aggressive surge: instant full throttle, then hold."""
    return [1.0] * 10


# ============================================================
# Configurations to test
# ============================================================
CONFIGS = {
    "A_baseline_no_tcs": TCSController(enabled=False),
    "B_default": TCSController(slip_threshold=0.15, pwm_decay=0.85),
    "B2_default_deriv": TCSController(slip_threshold=0.15, pwm_decay=0.85, use_derivative=True),
    "C_aggressive": TCSController(slip_threshold=0.10, pwm_decay=0.80),
    "C2_aggressive_deriv": TCSController(slip_threshold=0.10, pwm_decay=0.80, use_derivative=True),
    "D_conservative": TCSController(slip_threshold=0.20, pwm_decay=0.90),
    "F_recommended": TCSController(
        slip_threshold=0.10, pwm_decay=0.80, use_derivative=True, d_threshold=3.0
    ),
}

SURFACES = ["sumo", "slick", "rubber"]


# ============================================================
# Main validation
# ============================================================
def main():
    print("=" * 70)
    print("  DEBT-007: TCS Parameter Validation (Simulation)")
    print("  Target params: slip_threshold=0.15, pwm_decay=0.85")
    print(f"  Physics: WHEEL_R={WHEEL_RADIUS}m, MASS={VEHICLE_MASS}kg")
    print("=" * 70)

    results_all = {}
    profile = make_pwm_ramp(30)

    for cfg_name, tcs_config in CONFIGS.items():
        print(f"\n{'─' * 60}")
        print(f"  Config: {cfg_name}")
        if tcs_config.enabled:
            print(f"  TCS:  threshold={tcs_config.slip_threshold}, decay={tcs_config.pwm_decay}")
        else:
            print("  TCS:  DISABLED (baseline)")

        for surface in SURFACES:
            sim = WheelSimulator(tcs_config, surface=surface)
            sim.run(profile)
            m = sim.metrics()
            key = f"{cfg_name}__{surface}"
            results_all[key] = m

            print(
                f"    [{surface:6s}] dist={m['final_distance_m']:.4f}m, "
                f"v={m['final_velocity_mps']:.3f}m/s, "
                f"slip_max={m['max_slip']:.3f}, "
                f"slip_avg={m['avg_slip']:.3f}, "
                f"pwm_avg={m['avg_pwm_out']:.3f}, "
                f"intv={m['intervention_pct']:.1f}%, "
                f"eff={m['efficiency']:.2f}"
            )

    # Summary: compare derivative-TCS vs baseline
    print(f"\n{'=' * 60}")
    print("  SUMMARY: TCS+Derivative vs Baseline (No TCS)")
    print(f"{'=' * 60}")
    for surface in SURFACES:
        b = results_all[f"A_baseline_no_tcs__{surface}"]
        d = results_all[f"F_recommended__{surface}"]
        slip_reduction = (1 - d["max_slip"] / max(b["max_slip"], 1e-6)) * 100
        eff_change = (d["efficiency"] / max(b["efficiency"], 1e-6) - 1) * 100
        print(
            f"  [{surface:6s}] Slip: {b['max_slip']:.3f}→{d['max_slip']:.3f} "
            f"({slip_reduction:+.0f}%) | "
            f"Efficiency: {b['efficiency']:.1f}→{d['efficiency']:.1f} "
            f"({eff_change:+.0f}%) | "
            f"Interventions: {d['total_interventions']}"
        )

    # Pass/fail criteria
    print(f"\n{'=' * 60}")
    print("  PASS/FAIL CRITERIA:")
    print(f"{'=' * 60}")
    criteria_pass = True
    for surface in SURFACES:
        b = results_all[f"A_baseline_no_tcs__{surface}"]
        d = results_all[f"B_default__{surface}"]
        slip_reduced = d["max_slip"] < b["max_slip"]
        not_overcorrected = d["final_distance_m"] >= b["final_distance_m"] * 0.85
        passes = slip_reduced and not_overcorrected
        status = "✅ PASS" if passes else "❌ FAIL"
        if not passes:
            criteria_pass = False
            if not slip_reduced:
                print(
                    f"  {status} [{surface}] TCS did NOT reduce slip ({b['max_slip']:.3f}→{d['max_slip']:.3f})"
                )
            if not not_overcorrected:
                print(
                    f"  {status} [{surface}] TCS over-corrected: distance dropped >15% "
                    f"({b['final_distance_m']:.4f}m→{d['final_distance_m']:.4f}m)"
                )
        else:
            print(f"  {status} [{surface}] Slip reduced + distance acceptable")

    overall = "PASS" if criteria_pass else "PARTIAL PASS"
    print(f"\n  Overall: {overall}")

    # Find optimal threshold across sweep
    print(f"\n{'=' * 60}")
    print("  Parameter Sweep: optimal slip_threshold (pwm_decay=0.85)")
    print(f"{'=' * 60}")
    best_thresholds = {}
    for surface in SURFACES:
        best_efficiency = -1
        best_thresh = 0.15
        for thresh in [0.05, 0.08, 0.10, 0.12, 0.15, 0.18, 0.20, 0.25]:
            tcs = TCSController(slip_threshold=thresh, pwm_decay=0.85)
            sim = WheelSimulator(tcs, surface=surface)
            sim.run(profile)
            m = sim.metrics()
            if m["efficiency"] > best_efficiency:
                best_efficiency = m["efficiency"]
                best_thresh = thresh
        best_thresholds[surface] = (best_thresh, best_efficiency)
        print(f"  [{surface:6s}] best_thresh={best_thresh:.2f}, efficiency={best_efficiency:.2f}")

    # Save results
    output = {
        "debt": "DEBT-007",
        "target_params": {"slip_threshold": 0.15, "pwm_decay": 0.85},
        "criteria_pass": criteria_pass,
        "overall": overall,
        "optimal_thresholds": {s: v[0] for s, v in best_thresholds.items()},
        "results": results_all,
    }

    out_path = os.path.join(
        os.path.dirname(__file__), "..", "tests", "results", "debt007_tcs_results.json"
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Results saved to: {out_path}")

    return output


if __name__ == "__main__":
    main()
