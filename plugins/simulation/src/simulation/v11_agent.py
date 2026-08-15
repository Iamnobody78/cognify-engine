"""
v11_agent.py — V11 rule strategy ported to the 21-action lightweight env.

Control experiment (2026-08-05): the HIL 30/30 "100%" was vs a STATIONARY
opponent in a separate 1.0m physics (hil_closed_loop.py) — NOT a valid ceiling
benchmark for the V9 gate env (0.40m ring, 21 actions, LIVE opponent suite).
This class ports v11_select_action (virtual_mcu.py) onto the gate env's
7-dim obs and 21-action space to measure the true rule-design ceiling
against live opponents.

Adaptation notes:
  - obs[0..3] = edge_front/back/left/right (env: 1.0=center safe, 0.0=at edge)
      → maps 1:1 onto V11's edge_dist / front_edge semantics (1=center, 0=edge)
  - obs[4] = opponent_dist (m), obs[5] = opponent_angle in DEGREES
      (positive = CCW = left of robot heading)
  - local frame: local_x (right+) = -dist*sin(a), local_y (forward+) = dist*cos(a)
  - V11 actions 0/1/2/3/4/8/10 → 21-action {FW_MED, REV_SLOW, TURN_L_MED,
      TURN_R_MED, FW_LEFT_MED, FW_MAX, TURN_L_HARD}
"""

from __future__ import annotations

import math
from typing import Any, List

# V11 action -> 21-action space
_MAP = {0: 3, 1: 6, 2: 8, 3: 11, 4: 14, 8: 5, 10: 9}


class V11RuleAgent:
    """V11 3-phase closed-loop strategy (edge-protect → align → push)."""

    mode = "v11"

    OPP_CLOSE_DIST = 0.18  # push only when very close
    ALIGN_STRICT = 0.10  # strict alignment threshold (local_x)
    OPP_FRONT_THR = 0.15  # dead-zone for opponent directly in front
    PUSH_EDGE_SAFE = 0.40  # front must have >= this margin to push

    def __init__(self):
        self._action_history: List[int] = []

    def select_action(self, obs: Any) -> int:
        edge_f, edge_b, edge_l, edge_r = obs[0], obs[1], obs[2], obs[3]
        opp_dist = obs[4]
        opp_angle_deg = obs[5]

        edge_dist = min(edge_f, edge_b, edge_l, edge_r)
        front_edge = edge_f

        a = math.radians(opp_angle_deg)
        local_x = -opp_dist * math.sin(a)  # right-positive
        local_y = opp_dist * math.cos(a)  # forward-positive

        # RULE 0: edge protection (highest priority)
        if edge_dist < 0.12:
            return self._map(1)  # backward
        if edge_dist < 0.22:
            if front_edge < 0.25:
                return self._map(1)  # backward
            if front_edge < 0.40:
                return self._map(2)  # turn_left
            return self._map(4)  # forward_left

        # PHASE 1: aggressive alignment
        if local_y > 0.0 and opp_dist < 2.0:
            if abs(local_x) > self.ALIGN_STRICT:
                return self._map(2 if local_x < 0.0 else 3)

        # PHASE 2: approach
        if local_y > 0.0 and abs(local_x) < self.OPP_FRONT_THR:
            if opp_dist > self.OPP_CLOSE_DIST:
                if opp_dist < 1.2:
                    return self._map(8)  # push
                return self._map(0)  # forward

        # PHASE 3: push
        if (
            local_y > 0.0
            and abs(local_x) < self.ALIGN_STRICT
            and opp_dist < self.OPP_CLOSE_DIST
        ):
            if front_edge > self.PUSH_EDGE_SAFE:
                return self._map(8)  # push
            return self._map(0)  # forward

        # RULE 4: opponent to side → turn
        if abs(local_y) < 0.8:
            if local_x < -0.15:
                return self._map(2)
            if local_x > 0.15:
                return self._map(3)

        # RULE 5: opponent behind → turn around
        if local_y < -0.2:
            return self._map(2 if local_x < 0.0 else 3)

        # RULE 6: no opponent → spin
        return self._map(10)

    def _map(self, v11_action: int) -> int:
        action = _MAP.get(v11_action, 0)
        self._action_history.append(action)
        return action
