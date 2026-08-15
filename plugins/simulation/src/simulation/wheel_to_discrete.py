"""
wheel_to_discrete.py — V10 21-Level Action Space Mapping

Replaces the 11-level action space with 21 discrete actions for finer control.
Each action maps to (linear_x, angular_z) wheel commands for differential drive.

Architecture:
  - 7 Speed tiers: STOP, CREEP, SLOW, MED, FAST, MAX, REV_SLOW
  - 6 Turn tiers: MILD/MED/HARD for both LEFT and RIGHT
  - 8 Combined: forward + turn at various intensities

Why 21 levels (not 11):
  - 11-level lacks reverse (critical for edge recovery)
  - 11-level has only 3 forward speeds (misses creep for final approach)
  - 11-level turns are binary (no mild/medium/hard gradation)
  - 21-level adds reverse + creep + graded turns + fast-combos
"""

from enum import IntEnum
from typing import Tuple, List


class Action(IntEnum):
    """21 discrete actions for BottleSumo V10."""

    # ── Speed Tiers (0-6) ──
    STOP = 0  # (0.0, 0.0)
    CREEP_FWD = 1  # (0.08, 0.0) — ultra-slow final approach
    FW_SLOW = 2  # (0.15, 0.0) — conservative advance
    FW_MED = 3  # (0.27, 0.0) — moderate advance
    FW_FAST = 4  # (0.38, 0.0) — aggressive advance
    FW_MAX = 5  # (0.53, 0.0) — max speed rush (N20 300rpm @ 34mm wheel = 0.534 m/s)
    REV_SLOW = 6  # (-0.15, 0.0) — edge recovery reverse

    # ── Pure Turn Tiers (7-12) ──
    TURN_L_MILD = 7  # (0.0, 0.3)  — gentle left
    TURN_L_MED = 8  # (0.0, 0.6)  — moderate left
    TURN_L_HARD = 9  # (0.0, 1.0)  — sharp left
    TURN_R_MILD = 10  # (0.0, -0.3) — gentle right
    TURN_R_MED = 11  # (0.0, -0.6) — moderate right
    TURN_R_HARD = 12  # (0.0, -1.0) — sharp right

    # ── Combined Moves (13-20) ──
    FW_LEFT_MILD = 13  # (0.15, 0.3) — slow + gentle left
    FW_LEFT_MED = 14  # (0.15, 0.6) — slow + moderate left
    FW_LEFT_HARD = 15  # (0.23, 0.8) — faster + sharp left
    FW_RIGHT_MILD = 16  # (0.15, -0.3) — slow + gentle right
    FW_RIGHT_MED = 17  # (0.15, -0.6) — slow + moderate right
    FW_RIGHT_HARD = 18  # (0.23, -0.8) — faster + sharp right
    FW_LEFT_FAST = 19  # (0.30, 0.6) — fast advance + left turn
    FW_RIGHT_FAST = 20  # (0.30, -0.6) — fast advance + right turn

    def to_cmd(self) -> Tuple[float, float]:
        """Convert action to (linear_x, angular_z) wheel command."""
        return ACTION_MAP[self]

    @classmethod
    def size(cls) -> int:
        return len(ACTION_MAP)

    @classmethod
    def all(cls) -> List["Action"]:
        return list(Action)


# ── Action-to-Cmd Mapping ──
# Forward speed tiers scaled to physical max: N20 6V 300rpm @ 34mm wheel =
# MAX_WHEEL_VEL * WHEEL_RADIUS = 31.4 * 0.017 = 0.534 m/s (see models/motor_spec.json
# and .aionui/context/motor_consistency_audit.md). Angular tiers unchanged.
ACTION_MAP = {
    # Speed
    Action.STOP: (0.0, 0.0),
    Action.CREEP_FWD: (0.08, 0.0),
    Action.FW_SLOW: (0.15, 0.0),
    Action.FW_MED: (0.27, 0.0),
    Action.FW_FAST: (0.38, 0.0),
    Action.FW_MAX: (0.53, 0.0),
    Action.REV_SLOW: (-0.15, 0.0),
    # Turn
    Action.TURN_L_MILD: (0.0, 0.3),
    Action.TURN_L_MED: (0.0, 0.6),
    Action.TURN_L_HARD: (0.0, 1.0),
    Action.TURN_R_MILD: (0.0, -0.3),
    Action.TURN_R_MED: (0.0, -0.6),
    Action.TURN_R_HARD: (0.0, -1.0),
    # Combined
    Action.FW_LEFT_MILD: (0.15, 0.3),
    Action.FW_LEFT_MED: (0.15, 0.6),
    Action.FW_LEFT_HARD: (0.23, 0.8),
    Action.FW_RIGHT_MILD: (0.15, -0.3),
    Action.FW_RIGHT_MED: (0.15, -0.6),
    Action.FW_RIGHT_HARD: (0.23, -0.8),
    Action.FW_LEFT_FAST: (0.30, 0.6),
    Action.FW_RIGHT_FAST: (0.30, -0.6),
}

# ── Semantic Action Groups ──
ACTION_GROUPS = {
    "speed": [
        Action.STOP,
        Action.CREEP_FWD,
        Action.FW_SLOW,
        Action.FW_MED,
        Action.FW_FAST,
        Action.FW_MAX,
        Action.REV_SLOW,
    ],
    "turn": [
        Action.TURN_L_MILD,
        Action.TURN_L_MED,
        Action.TURN_L_HARD,
        Action.TURN_R_MILD,
        Action.TURN_R_MED,
        Action.TURN_R_HARD,
    ],
    "combined": [
        Action.FW_LEFT_MILD,
        Action.FW_LEFT_MED,
        Action.FW_LEFT_HARD,
        Action.FW_RIGHT_MILD,
        Action.FW_RIGHT_MED,
        Action.FW_RIGHT_HARD,
        Action.FW_LEFT_FAST,
        Action.FW_RIGHT_FAST,
    ],
}

# ── Safety Actions (for edge proximity) ──
SAFE_ACTIONS_WHEN_EDGE_CLOSE = [
    Action.STOP,
    Action.REV_SLOW,
    Action.TURN_L_MILD,
    Action.TURN_R_MILD,
    Action.CREEP_FWD,
]


# ── Heuristic Policy (V10, 21-level aware) ──
def heuristic_policy_v10(angle: float, dist: float, edge_margin: float = 1.0) -> int:
    """
    Rule-based policy using 21-level action space.

    Args:
        angle: relative angle to opponent in degrees (-180 to 180)
        dist: distance to opponent in meters
        edge_margin: minimum edge sensor value (1.0 = safe, 0.0 = on edge)

    Returns:
        Action enum value (0-20)
    """
    # CRITICAL: edge recovery — must NOT fall off
    if edge_margin < 0.3:
        # On edge — reverse and turn away
        return Action.REV_SLOW

    if edge_margin < 0.5:
        # Close to edge — only safe moves
        return Action.CREEP_FWD

    # No opponent detected
    if dist >= 3.9:
        return Action.TURN_L_MED  # search rotation

    # Opponent detected — categorize by distance zone
    if dist < 0.1:
        # Point blank: max push, slight turn to hook
        if abs(angle) < 10:
            return Action.FW_MAX
        elif angle > 0:
            return Action.FW_RIGHT_HARD
        else:
            return Action.FW_LEFT_HARD

    elif dist < 0.3:
        # Close range: fast approach with correction
        if abs(angle) < 15:
            return Action.FW_FAST
        elif 15 <= angle < 45:
            return Action.FW_LEFT_MED
        elif -45 < angle <= -15:
            return Action.FW_RIGHT_MED
        elif angle >= 45:
            return Action.TURN_L_HARD
        else:
            return Action.TURN_R_HARD

    elif dist < 0.8:
        # Medium range: moderate approach + gentle turn
        if abs(angle) < 20:
            return Action.FW_MED
        elif 20 <= angle < 60:
            return Action.FW_LEFT_MILD
        elif -60 < angle <= -20:
            return Action.FW_RIGHT_MILD
        elif angle >= 60:
            return Action.TURN_L_MED
        else:
            return Action.TURN_R_MED

    else:
        # Far range: approach with wide correction
        if abs(angle) < 30:
            return Action.FW_SLOW
        elif angle >= 30:
            return Action.TURN_L_MILD
        else:
            return Action.TURN_R_MILD


# ── 11-to-21 Compatibility Bridge ──
def legacy_action_to_v10(legacy_action: int) -> int:
    """
    Map old 11-level action to nearest 21-level equivalent.
    For gradual migration from V9 to V10.
    """
    BRIDGE = {
        0: Action.STOP,  # STOP → STOP
        1: Action.FW_SLOW,  # FW_SLOW → FW_SLOW
        2: Action.FW_MED,  # FW_MED → FW_MED
        3: Action.FW_FAST,  # FW_FAST → FW_FAST
        4: Action.TURN_L_HARD,  # TURN_LEFT → TURN_L_HARD
        5: Action.TURN_R_HARD,  # TURN_RIGHT → TURN_R_HARD
        6: Action.FW_LEFT_MED,  # FW_LEFT → FW_LEFT_MED
        7: Action.FW_RIGHT_MED,  # FW_RIGHT → FW_RIGHT_MED
        8: Action.FW_LEFT_MILD,  # TURN_SLOW_L → FW_LEFT_MILD
        9: Action.FW_RIGHT_MILD,  # TURN_SLOW_R → FW_RIGHT_MILD
        10: Action.STOP,  # EMERGENCY_STOP → STOP
    }
    return BRIDGE.get(legacy_action, Action.STOP)


# ── Test ──
if __name__ == "__main__":
    print(f"V10 Action Space: {Action.size()} discrete actions")
    print(f"\nSpeed tiers: {len(ACTION_GROUPS['speed'])}")
    print(f"Turn tiers: {len(ACTION_GROUPS['turn'])}")
    print(f"Combined moves: {len(ACTION_GROUPS['combined'])}")
    print(f"Safe actions (edge close): {len(SAFE_ACTIONS_WHEN_EDGE_CLOSE)}")

    # Test heuristic policy
    print("\nHeuristic policy test:")
    test_cases = [
        (0, 0.05, 1.0),  # point blank, centered
        (30, 0.2, 1.0),  # close, 30° off
        (-60, 0.5, 1.0),  # medium, -60° off
        (120, 2.0, 1.0),  # far, 120° off
        (0, 0.05, 0.2),  # point blank, near edge
    ]
    for angle, dist, margin in test_cases:
        action = heuristic_policy_v10(angle, dist, margin)
        cmd = ACTION_MAP[action]
        print(
            f"  angle={angle:+.0f}° dist={dist:.2f}m edge={margin:.1f} → "
            f"Action({action})={Action(action).name} → cmd={cmd}"
        )
