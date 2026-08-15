"""
reward_functions.py — V10 Progressive Reward Functions

Fixes the "edge fear" problem from V9:
  - V9: binary edge penalty (-100 at 2cm) → robot learns to panic near edges
  - V10: progressive penalty + early warning + safety reward → smooth learning

Design principles:
  1. No sudden death — edge penalty ramps up gradually
  2. Early warning — small penalty before critical zone
  3. Positive reinforcement for staying safe
  4. Directional awareness — penalize heading TOWARD edge, reward heading AWAY

V11 additions (Meta-Harness BayesOpt):
  - edge_penalty_weight: global scale for all edge penalties (from CausalPrior BO)
  - push_threshold: adjustable push bonus distance threshold
"""

from typing import Tuple
import math


# ── Edge Zone Constants (cm from dohyo edge) ──
EDGE_CRITICAL = 1.0  # < 1cm: true fall (terminal)
EDGE_DANGER = 3.0  # 1-3cm: heavy penalty zone
EDGE_WARNING = 6.0  # 3-6cm: moderate penalty + early warning
EDGE_CAUTION = 10.0  # 6-10cm: mild penalty, encourage retreat
EDGE_SAFE = 20.0  # > 10cm: safe zone, no edge penalty


class V10Reward:
    """
    V10 progressive reward function with edge awareness.

    Replaces the V9 binary edge penalty with a smooth gradient.

    V11: Supports edge_penalty_weight (global scale) and push_threshold from
         CausalPrior Bayesian Optimization (Meta-Harness).

    Usage:
        reward_fn = V10Reward(edge_penalty_weight=71.6, push_threshold=0.28)
        reward, done = reward_fn.compute(edge_sensors, opp_dist, opp_angle, speed, heading_to_edge)
    """

    def __init__(
        self,
        edge_critical: float = EDGE_CRITICAL,
        edge_danger: float = EDGE_DANGER,
        edge_warning: float = EDGE_WARNING,
        edge_caution: float = EDGE_CAUTION,
        edge_safe: float = EDGE_SAFE,
        edge_penalty_weight: float = 1.0,
        push_threshold: float = 0.2,
    ):
        self.edge_critical = edge_critical
        self.edge_danger = edge_danger
        self.edge_warning = edge_warning
        self.edge_caution = edge_caution
        self.edge_safe = edge_safe
        self.edge_penalty_weight = edge_penalty_weight  # global scale for edge penalties
        self.push_threshold = push_threshold  # push bonus distance threshold (m)

    def compute_edge_reward(
        self,
        edge_front: float,
        edge_back: float,
        edge_left: float,
        edge_right: float,
        heading_to_edge: float = 0.0,
        robot_out_of_bounds: bool = False,
    ) -> Tuple[float, bool]:
        """
        Compute progressive edge reward.

        Args:
            edge_front/back/left/right: normalized edge sensors [0.0=at_edge, 1.0=center]
            heading_to_edge: float, how much robot is heading toward edge
                             positive = heading toward nearest edge
                             0 = parallel to edge
                             negative = heading away from edge
            robot_out_of_bounds: authoritative out-of-dohyo flag from the env
                                 (robot CENTER beyond ring edge).

        Returns:
            (reward_delta, is_terminal)

        FIXED 2026-08-05: the probe-based terminal (edge_min < 0.05) fired when a
        sensor PROBE 7.5cm ahead of the robot center crossed the rim — i.e. at
        center r > 0.325 in a 0.40m ring, killing the robot while its body was
        still 75% on the dohyo. The env now passes the authoritative
        robot_out_of_bounds (center-based); the probe check remains only as a
        backstop for callers that do not pass the flag.
        """
        edge_min = min(edge_front, edge_back, edge_left, edge_right)

        # ── Terminal: true fall (authoritative center-based) ──
        if robot_out_of_bounds:
            return -150.0, True

        # ── Terminal: probe-based backstop (only if flag not provided) ──
        if edge_min < self.edge_critical / 20.0:  # normalized to 0-1 range
            return -150.0, True

        reward = 0.0
        done = False
        w = self.edge_penalty_weight  # shorthand

        # ── Progressive penalty zones ──
        # edge_min ranges from 0 (at edge) to 1 (center)
        # All edge penalties scaled by edge_penalty_weight (BayesOpt optimized)

        # Danger zone: edge_min < 0.15 (within 3cm)
        if edge_min < 0.15:
            # Heavy penalty: -10 to -40 depending on proximity
            danger_factor = (0.15 - edge_min) / 0.15  # 0 to 1
            reward += -40.0 * danger_factor * w

            # Additional penalty if heading toward edge
            if heading_to_edge > 0:
                reward += -20.0 * heading_to_edge * w

            # Near-critical warning
            if edge_min < 0.05:
                reward += -15.0 * w  # "you're about to fall!"

        # Warning zone: 0.15 <= edge_min < 0.30 (3-6cm)
        elif edge_min < 0.30:
            warning_factor = (0.30 - edge_min) / 0.15  # 0 to 1
            reward += -10.0 * warning_factor * w

            if heading_to_edge > 0:
                reward += -5.0 * heading_to_edge * w

        # Caution zone: 0.30 <= edge_min < 0.50 (6-10cm)
        elif edge_min < 0.50:
            caution_factor = (0.50 - edge_min) / 0.20
            # Mild penalty
            reward += -3.0 * caution_factor * w

            # Small reward for staying safe (positive reinforcement)
            reward += 0.5 * (1.0 - caution_factor) * min(w, 1.0)

        # Safe zone: edge_min >= 0.50 (>10cm)
        else:
            # Small positive reward for being in safe zone
            safety_bonus = 0.2 * (edge_min - 0.50) / 0.50  # max 0.2
            reward += safety_bonus * min(w, 1.0)  # don't over-reward with high w

            # Extra bonus for actively retreating from edge
            if heading_to_edge < -0.3:
                reward += 0.3 * min(w, 1.0)

        return reward, done

    def compute_opponent_reward(self, opp_dist: float, opp_angle: float, speed: float) -> float:
        """
        Compute opponent interaction reward.

        Args:
            opp_dist: distance to opponent (0-4m)
            opp_angle: relative angle to opponent (-180 to 180 degrees)
            speed: current robot speed (linear velocity)

        Returns:
            reward delta
        """
        reward = 0.0

        # ── 1. Approach reward: closer is better ──
        if opp_dist < 1.5:
            approach_reward = 3.0 * (1.0 - opp_dist / 1.5)  # max 3.0 at 0m
            reward += approach_reward

        # ── 2. Alignment reward: facing opponent is better ──
        abs_angle = abs(opp_angle)
        if abs_angle < 90 and opp_dist < 1.0:
            alignment_reward = 2.0 * (1.0 - abs_angle / 90.0)  # max 2.0 at 0°
            reward += alignment_reward

        # ── 3. Push bonus: high speed + close + aligned = push! ──
        # push_threshold from BayesOpt (default 0.2m, optimal 0.285m)
        if opp_dist < self.push_threshold and abs_angle < 30 and speed > 0.3:
            reward += 8.0  # strong push

        # ── 4. Standing still penalty (encourage activity) ──
        if speed < 0.05 and opp_dist < 0.5:
            reward -= 1.0  # don't just sit there

        # ── 5. Survival bonus ──
        reward += 0.05

        return reward

    def compute(
        self,
        edge_sensors: Tuple[float, float, float, float],
        opp_dist: float,
        opp_angle: float,
        speed: float,
        heading_to_edge: float = 0.0,
        opp_out_of_bounds: bool = False,
        robot_out_of_bounds: bool = False,
    ) -> Tuple[float, bool]:
        """
        Full reward computation combining edge awareness + opponent interaction.

        Args:
            edge_sensors: (front, back, left, right) normalized [0,1]
            opp_dist: distance to opponent in meters
            opp_angle: relative angle in degrees (-180 to 180)
            speed: linear velocity
            heading_to_edge: 0-1, how much robot heading faces nearest edge
            opp_out_of_bounds: True if opponent has fallen off
            robot_out_of_bounds: True if robot has fallen off (authoritative,
                                 center-based; avoids probe-offset false deaths)

        Returns:
            (total_reward, is_terminal)
        """
        edge_f, edge_b, edge_l, edge_r = edge_sensors

        # ── Edge reward ──
        edge_reward, edge_done = self.compute_edge_reward(
            edge_f, edge_b, edge_l, edge_r, heading_to_edge, robot_out_of_bounds
        )

        if edge_done:
            return edge_reward, True

        # ── Win condition ──
        if opp_out_of_bounds:
            return 200.0, True

        # ── Opponent reward ──
        opp_reward = self.compute_opponent_reward(opp_dist, opp_angle, speed)

        total = edge_reward + opp_reward
        return total, False


# ── Heading-to-Edge Computation ──
def compute_heading_to_edge(
    robot_theta: float, robot_x: float, robot_y: float, dohyo_radius: float
) -> float:
    """
    Compute how much the robot is heading toward the nearest edge.

    Returns:
        float in [-1, 1]:
            +1.0 = heading directly toward nearest edge (bad)
             0.0 = heading parallel to edge
            -1.0 = heading directly away from edge (good)
    """
    # Direction from robot to dohyo center
    to_center_x = -robot_x
    to_center_y = -robot_y
    to_center_angle = math.atan2(to_center_y, to_center_x)

    # Robot heading
    heading = robot_theta

    # Angle between heading and "toward center" direction
    angle_diff = (to_center_angle - heading + math.pi) % (2 * math.pi) - math.pi

    # Dot product: cos(angle_diff)
    # +1 = heading toward center (away from edge) → safe
    # -1 = heading away from center (toward edge) → dangerous
    heading_to_center = math.cos(angle_diff)
    heading_to_edge = -heading_to_center  # invert: +1 = toward edge

    return heading_to_edge


# ── Default V10 Reward Instance ──
default_reward = V10Reward()


# ── Test ──
if __name__ == "__main__":
    r = V10Reward()

    print("=" * 50)
    print(" V10 Progressive Edge Reward — Test Cases")
    print("=" * 50)

    test_cases = [
        # (edge_sensors, opp_dist, opp_angle, speed, heading_to_edge)
        ((1.0, 1.0, 1.0, 1.0), 2.0, 0, 0.0, 0.0),  # center, far from opp
        ((0.05, 1.0, 0.8, 0.9), 0.3, 15, 0.4, 0.8),  # near edge, close to opp, heading out
        ((0.03, 0.9, 0.7, 0.8), 0.05, 0, 0.7, 0.2),  # critical edge, pushing opp
        ((0.6, 0.6, 0.6, 0.6), 0.1, 10, 0.6, 0.0),  # safe, point blank
        ((0.02, 0.9, 0.6, 0.5), 1.0, 90, 0.2, 0.5),  # almost edge, opp far
    ]

    for edge, dist, angle, speed, hte in test_cases:
        reward, done = r.compute(edge, dist, angle, speed, hte, False)
        edge_reward, edge_done = r.compute_edge_reward(*edge, hte)
        edge_min = min(edge)
        print(f"\n  edge_min={edge_min:.2f} heading_to_edge={hte:+.1f}")
        print(f"    edge_reward={edge_reward:+.1f} edge_done={edge_done}")
        print(f"    total_reward={reward:+.1f} done={done}")

    print("\n✅ V10 Reward Functions ready")
