#!/usr/bin/env python3
"""
ABDL Action Bridge — Rule-to-Action Mapping Engine
===================================================
Maps ABDL rule evaluation results to BottleSumo 21-level Action space.

Flow:
  1. Observations -> WorldState (7-dim obs -> sensor/metric dict)
  2. WorldState -> ABDLEngine.evaluate() -> triggered rules
  3. Triggered rules -> PolicyExecutor -> Action enum (0-20)
  4. Action -> ACTION_MAP -> (linear_x, angular_z) wheel command

This is the KEY innovation of P1: proving that a formal rule language
(ABDL) can drive physics simulation with performance comparable to
hand-coded heuristics.
"""
import math
import random
import sys
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure bottlesumo_pi on path
_BASE = Path(__file__).resolve().parent.parent.parent
if str(_BASE) not in sys.path:
    sys.path.insert(0, str(_BASE))

import numpy as np
from simulation.wheel_to_discrete import Action, ACTION_MAP, SAFE_ACTIONS_WHEN_EDGE_CLOSE
from core.meta_language.abdl_engine import ABDLEngine, ConditionEvaluator, Rule


# ── Policy IDs ──────────────────────────────────────────────────────────────

class PolicyID(str, Enum):
    """ABDL rule action EXECUTE targets."""
    PolicyEdgeRecovery = "PolicyEdgeRecovery"
    PolicyEdgeRetreat = "PolicyEdgeRetreat"
    PolicyStuckRecovery = "PolicyStuckRecovery"
    PolicyPursueOpponent = "PolicyPursueOpponent"
    PolicySearchSweep = "PolicySearchSweep"
    PolicyCautiousSearch = "PolicyCautiousSearch"
    PolicyRushPush = "PolicyRushPush"
    PolicyFlankRight = "PolicyFlankRight"
    PolicyFlankLeft = "PolicyFlankLeft"
    PolicySpeedBoost = "PolicySpeedBoost"
    PolicyCautiousEdge = "PolicyCautiousEdge"
    PolicyExploreWide = "PolicyExploreWide"
    PolicyDefensiveBrace = "PolicyDefensiveBrace"

    @classmethod
    def from_action_str(cls, action_str: str) -> Optional["PolicyID"]:
        """Parse EXECUTE(PolicyName, ...) from ABDL action strings."""
        import re
        match = re.search(r"EXECUTE\((\w+)", action_str)
        if match:
            try:
                return cls(match.group(1))
            except ValueError:
                return None
        return None


# ── World State Builder ──────────────────────────────────────────────────────

class WorldStateBuilder:
    """Converts BottleSumo observation vector to ABDL world state dict.

    Actual observation format (7-dim from lightweight_env._get_obs):
      [edge_front, edge_back, edge_left, edge_right, opp_dist, opp_angle, robot_speed]
         0          1         2          3          4         5          6
    """

    def __init__(self, arena_size: float = 2.0, max_dist: float = 4.0):
        self.arena_size = arena_size
        self.max_dist = max_dist

    def build(self, obs: np.ndarray, info: dict = None,
              vision: dict = None) -> Dict[str, Any]:
        """Convert a BottleSumo observation to ABDL world state.

        vision (Phase B, PM 2026-08-06): 可选的 VLM 洞察 dict
        (vision_proxy /insight 标准化输出: objects/robot/opponent/edge_min/
        zone/confidence/...)。存在时注入 world_state["vision"] 供
        _apply_vision_softening 消费; 缺省 None -> 零影响 (门回归不倒退)。
        """
        info = info or {}
        obs_len = len(obs)

        # Parse 7-dim observation
        edge_f = float(obs[0]) if obs_len > 0 else 1.0
        edge_b = float(obs[1]) if obs_len > 1 else 1.0
        edge_l = float(obs[2]) if obs_len > 2 else 1.0
        edge_r = float(obs[3]) if obs_len > 3 else 1.0
        opp_dist = float(obs[4]) if obs_len > 4 else self.max_dist
        opp_angle = float(obs[5]) if obs_len > 5 else 0.0
        agent_speed = float(obs[6]) if obs_len > 6 else 0.0

        # Compute edge proximity from 4 edge sensors (0=ok, 1=at edge)
        edge_prox = 1.0 - min(edge_f, edge_b, edge_l, edge_r)

        # Opponent detection: within ToF range and not max
        opponent_found = opp_dist < self.max_dist - 0.1

        # Push force from info or estimate
        push_force = info.get("push_force", 0.0)

        ws = {
            "sensors": {
                "edge_proximity": edge_prox,
                "edge_front": edge_f,
                "edge_back": edge_b,
                "edge_left": edge_l,
                "edge_right": edge_r,
                "opponent_dist": opp_dist,
                "opponent_angle": opp_angle,
                "opponent_found": opponent_found,
                "push_force": push_force,
                "agent_speed": agent_speed,
                "steps_remaining": info.get("steps_remaining", 200),
                "stuck_counter": info.get("stuck_counter", 0),
            },
            "metrics": {
                "opponent_angle": opp_angle,
                "opponent_dist": opp_dist,
                "edge_proximity": edge_prox,
                "agent_speed": agent_speed,
            },
            "state": {
                "edge_front": edge_f,
                "edge_back": edge_b,
                "edge_left": edge_l,
                "edge_right": edge_r,
            },
            "config": {
                "arena_size": self.arena_size,
                "max_dist": self.max_dist,
            },
            "entities": [
                "opponent_found" if opponent_found else None,
            ],
        }
        if vision:
            ws["vision"] = vision
        return ws

    def reset(self):
        """Reset state for new episode."""
        pass  # No persistent state needed with new observation format


# ── Policy Executor ──────────────────────────────────────────────────────────

class PolicyExecutor:
    """Executes ABDL policies and maps them to Action enum values."""

    def __init__(self):
        self._search_phase = 0  # For sweep patterns
        self._explore_pattern = 0  # For zigzag

    def execute(self, policy: PolicyID, world_state: Dict[str, Any],
                params: dict = None) -> int:
        """Execute a policy and return an Action enum value.

        Args:
            policy: The triggered policy ID
            world_state: Current ABDL world state
            params: Optional parameters from the rule action

        Returns:
            Action enum integer value (0-20)
        """
        sensors = world_state.get("sensors", {})
        params = params or {}

        # ── L0: Safety ──
        if policy == PolicyID.PolicyEdgeRecovery:
            return self._edge_recovery(sensors)
        elif policy == PolicyID.PolicyEdgeRetreat:
            return self._edge_retreat(sensors)
        elif policy == PolicyID.PolicyStuckRecovery:
            return self._stuck_recovery()

        # ── L1: Core Tactics ──
        elif policy == PolicyID.PolicyPursueOpponent:
            angle = params.get("angle", sensors.get("opponent_angle", 0))
            dist = params.get("dist", sensors.get("opponent_dist", 1.0))
            return self._pursue_opponent(angle, dist)
        elif policy == PolicyID.PolicySearchSweep:
            return self._search_sweep()
        elif policy == PolicyID.PolicyCautiousSearch:
            return self._cautious_search()

        # ── L2: Advanced ──
        elif policy == PolicyID.PolicyRushPush:
            return Action.FW_MAX.value
        elif policy == PolicyID.PolicyFlankRight:
            # FIXED 2026-08-05 (iter 3): hybrid flank.
            #   * >45° heading error: TURN_R_HARD — fastest realignment, safe
            #     since the opponent is off-axis.
            #   * <=45°: the choice depends on whether the opponent is PRESSING
            #     or RETREATING:
            #       - in contact (dist < 0.20): FW_RIGHT_HARD arc — keeps 0.23
            #         m/s thrust so a pressing opponent (aggressive) can't shove
            #         a stationary robot;
            #       - separated (dist >= 0.20): TURN_R_MED pure turn — converges
            #         the residual heading error (an arc locks in side-contact
            #         at ~-37° because its 0.29m orbit can't fit the 0.15m
            #         contact radius) against retreating opponents (defensive).
            angle = params.get("angle", sensors.get("opponent_angle", 0))
            dist = params.get("dist", sensors.get("opponent_dist", 0.5))
            if abs(angle) > 40:
                return Action.TURN_R_HARD.value
            if dist < 0.20:
                return Action.FW_RIGHT_HARD.value
            return Action.TURN_R_MED.value
        elif policy == PolicyID.PolicyFlankLeft:
            angle = params.get("angle", sensors.get("opponent_angle", 0))
            dist = params.get("dist", sensors.get("opponent_dist", 0.5))
            if abs(angle) > 40:
                return Action.TURN_L_HARD.value
            if dist < 0.20:
                return Action.FW_LEFT_HARD.value
            return Action.TURN_L_MED.value

        # ── L3: Heuristic ──
        elif policy == PolicyID.PolicySpeedBoost:
            return Action.FW_FAST.value
        elif policy == PolicyID.PolicyCautiousEdge:
            return self._cautious_edge(sensors)
        elif policy == PolicyID.PolicyExploreWide:
            return self._explore_wide()
        elif policy == PolicyID.PolicyDefensiveBrace:
            return self._defensive_brace(sensors)

        # Default: random safe action
        return random.choice(SAFE_ACTIONS_WHEN_EDGE_CLOSE).value

    # ── Policy Implementations ──

    def _edge_recovery(self, sensors: dict) -> int:
        """Emergency recovery when critically near edge: always back away.

        Edge sensors are 1.0 = safe, 0.0 = at edge.  Backing away is the only
        reliable action in the danger zone (matches v11: edge_dist<0.12 ->
        backwards).  No randomness: random turns may face the edge again.
        """
        return Action.REV_SLOW.value

    def _edge_retreat(self, sensors: dict) -> int:
        """Cautious retreat when approaching edge: steer toward the safer side.

        Direction-aware, deterministic:
        - front edge danger -> reverse
        - otherwise turn toward the side with MORE clearance.
        """
        edge_f = sensors.get("edge_front", 1.0)
        edge_b = sensors.get("edge_back", 1.0)
        edge_l = sensors.get("edge_left", 1.0)
        edge_r = sensors.get("edge_right", 1.0)

        # Front is the most dangerous direction -> back off
        if edge_f < 0.3:
            return Action.REV_SLOW.value
        # Steer toward the side with more clearance
        if edge_l < edge_r:  # left is closer to edge -> turn right
            return Action.TURN_R_MILD.value
        if edge_r < edge_l:  # right is closer to edge -> turn left
            return Action.TURN_L_MILD.value
        # Symmetric -> reverse is safest
        return Action.REV_SLOW.value

    def _stuck_recovery(self) -> int:
        """Random movement to break free when stuck."""
        recovery = [
            Action.REV_SLOW.value,
            Action.TURN_L_HARD.value,
            Action.TURN_R_HARD.value,
            Action.FW_FAST.value,
        ]
        return random.choice(recovery)

    def _pursue_opponent(self, angle_deg: float, dist: float) -> int:
        """Pursue opponent based on angle and distance.

        Environment convention: opponent_angle is the signed relative angle in
        degrees, POSITIVE = opponent to the LEFT of robot heading
        (atan2 CCW-positive, see lightweight_env._get_obs).
        """
        abs_angle = abs(angle_deg)

        # Directly ahead -> charge (only when close; matches v11 0.18m window)
        if abs_angle < 15 and dist < 0.22:
            return Action.FW_MAX.value
        elif abs_angle < 15:
            return Action.FW_FAST.value
        elif abs_angle < 30:
            return Action.FW_MED.value

        # Slight angle -> combined move (positive angle = LEFT)
        if angle_deg > 0:  # Opponent to left
            if dist < 0.3:
                return Action.FW_LEFT_MILD.value
            elif dist < 0.6:
                return Action.FW_LEFT_MED.value
            else:
                return Action.FW_LEFT_FAST.value
        else:  # Opponent to right (angle <= 0)
            if dist < 0.3:
                return Action.FW_RIGHT_MILD.value
            elif dist < 0.6:
                return Action.FW_RIGHT_MED.value
            else:
                return Action.FW_RIGHT_FAST.value

    def _search_sweep(self) -> int:
        """Rotating sweep to find opponent."""
        self._search_phase = (self._search_phase + 1) % 24

        if self._search_phase < 8:
            return Action.TURN_L_MILD.value  # Sweep left
        elif self._search_phase < 16:
            return Action.TURN_R_MILD.value  # Sweep right
        else:
            return Action.FW_SLOW.value  # Move forward to avoid staying put

    def _cautious_search(self) -> int:
        """Search while staying away from edge."""
        return random.choice([Action.TURN_L_MILD.value, Action.TURN_R_MILD.value,
                              Action.CREEP_FWD.value])

    def _cautious_edge(self, sensors: dict) -> int:
        """Reduce speed and widen turns near edge."""
        return random.choice([Action.CREEP_FWD.value, Action.TURN_L_MILD.value,
                              Action.TURN_R_MILD.value])

    def _explore_wide(self) -> int:
        """Zigzag exploration pattern."""
        self._explore_pattern = (self._explore_pattern + 1) % 20
        if self._explore_pattern < 8:
            return Action.FW_SLOW.value
        elif self._explore_pattern < 10:
            return Action.TURN_L_MILD.value
        elif self._explore_pattern < 12:
            return Action.TURN_R_MILD.value
        elif self._explore_pattern < 16:
            return Action.FW_MED.value
        else:
            return Action.CREEP_FWD.value

    def _defensive_brace(self, sensors: dict) -> int:
        """Brace against push force."""
        # Push back or hold position
        return Action.FW_MED.value  # Push back to counteract force

    def reset(self):
        """Reset internal state for new episode."""
        self._search_phase = 0
        self._explore_pattern = 0


# ── ABDL Decision Maker ──────────────────────────────────────────────────────

class ABDLDecisionMaker:
    """ABDL decision maker with cached ConditionEvaluator for speed.

    Uses the full ABDL regex-based engine for correct rule matching,
    but caches the ConditionEvaluator to avoid re-allocation per step.
    """

    def __init__(self, rules_file: str = None):
        if rules_file is None:
            rules_file = str(
                Path(__file__).resolve().parent.parent.parent
                / "governance" / "meta_language" / "simulation_rules.abdl"
            )

        self.builder = WorldStateBuilder()
        self.executor = PolicyExecutor()
        self.engine = ABDLEngine(project_root=str(_BASE))
        self.engine.rules_file = Path(rules_file)
        self.engine.load()

        # Pre-compute policy mapping
        self._rule_policy_map = {}
        for rule in self.engine.rules.values():
            pid = PolicyID.from_action_str(rule.action)
            if pid:
                self._rule_policy_map[rule.id] = pid

    def decide(self, world_state: Dict[str, Any]) -> int:
        """Full ABDL evaluation with correct ConditionEvaluator."""
        return self.decide_traced(world_state)[0]

    def decide_traced(self, world_state: Dict[str, Any]) -> Tuple[int, dict]:
        """G3: decide + return (action, decision_trace) for visualization/debugging.

        Trace contains: rule_id, policy_id, action, reason — lets the RViz overlay
        show *which* ABDL rule fired and why, not just the resulting action int.
        """
        results = self.engine.evaluate(world_state)
        trace = {
            "rule_id": None,
            "policy_id": None,
            "action": None,
            "reason": "",
            "rules_triggered": [],
            "mode": "abdl",
        }
        if not results:
            trace["action"] = Action.FW_SLOW.value
            trace["reason"] = "no rule triggered -> default FW_SLOW"
            return Action.FW_SLOW.value, trace

        top = results[0]
        trace["rules_triggered"] = [r.rule.id for r in results]
        trace["rule_id"] = top.rule.id
        trace["reason"] = getattr(top, "reason", "")
        pid = self._rule_policy_map.get(top.rule.id)
        if pid is None:
            trace["action"] = Action.FW_SLOW.value
            trace["reason"] = f"{top.rule.id} has no mapped policy -> default FW_SLOW"
            return Action.FW_SLOW.value, trace

        params = self._resolve_params(top.action,
                                        world_state.get("sensors", {}),
                                        world_state.get("metrics", {}))
        action = self.executor.execute(pid, world_state, params)
        trace["action"] = int(action)
        trace["policy_id"] = pid.name
        # ── Phase B (PM 2026-08-06 裁决): 视觉洞察软化规则边界 ──
        # world_state["vision"] 存在时按 PM 两个指定场景软化; 无 vision /
        # 低置信度 -> 零影响 (门回归不倒退保证)。不修改 simulation_rules.abdl。
        if world_state.get("vision"):
            action, softening = self._apply_vision_softening(
                int(action), world_state, top.rule.id)
            if softening:
                trace["vision_softening"] = softening
                trace["action"] = int(action)
        return int(action), trace

    # ──────────────────────────────────────────────────────────────────────────
    # Phase B (PM 2026-08-06): _apply_vision_softening — 视觉洞察决策辅助
    # 范围强约束 (PM): 仅两个场景; 不改 simulation_rules.abdl; 门控与 A4 一致。
    # ──────────────────────────────────────────────────────────────────────────
    VISION_GATE = 0.6               # confidence < 0.6 不软化 (防编造, 与 A4 门控一致)
    VISION_EDGE_MIN_FLANK = 0.20    # 场景①: CLOSE-PUSH 下 edge_min < 0.20 提前 FLANK
    VISION_DANGER_SPEED_CAP = 0.45  # 场景②: OPPONENT-FOUND 下 zone==danger 线速度上限 (PM 目标)
    CLOSE_PUSH_RULE_IDS = ("SIM-ADVANCED-CLOSE-PUSH",)
    OPPONENT_FOUND_RULE_IDS = ("SIM-TACTIC-OPPONENT-FOUND",)
    # 离散动作空间无 0.45 m/s 档 (0.08/0.15/0.27/0.38/0.53) ->
    # 保守取 FW_FAST(0.38) 作为 <= 0.45 的最近档 (比 PM 目标更安全, 降速 28%)
    VISION_DANGER_SPEED_ACTION = Action.FW_FAST.value

    def _apply_vision_softening(self, action: int, world_state: dict,
                                rule_id: str) -> Tuple[int, dict]:
        """视觉洞察软化规则边界 — 仅限 PM 指定的两个场景。

        场景① CLOSE-PUSH + vision.edge_min < 0.20
            -> 提前触发 FLANK 规避 (而非死等到 opponent_dist < 0.3)
        场景② OPPONENT-FOUND + vision.zone == danger
            -> 线速度 > 0.45 的输出降速至 0.38 (PM 目标 0.45, 离散近似)

        返回 (softened_action, softening_trace); 未命中场景 / 门控不过 ->
        (原 action, {}) — 保证无 vision 时行为逐位不变。
        """
        vision = world_state.get("vision") or {}
        if vision.get("confidence", 0.0) < self.VISION_GATE:
            return action, {}   # 门控: 低置信度不软化

        em = vision.get("edge_min")
        zone = vision.get("zone")

        # 场景①: CLOSE-PUSH + edge_min < 0.20 -> 提前 FLANK
        if rule_id in self.CLOSE_PUSH_RULE_IDS \
                and isinstance(em, (int, float)) and em < self.VISION_EDGE_MIN_FLANK:
            sensors = world_state.get("sensors", {})
            angle = sensors.get("opponent_angle", 0.0)
            dist = sensors.get("opponent_dist", 0.5)
            pid = (PolicyID.PolicyFlankLeft if angle >= 0
                   else PolicyID.PolicyFlankRight)
            flank = self.executor.execute(pid, world_state,
                                          {"angle": angle, "dist": dist})
            return int(flank), {
                "applied": True,
                "scenario": "S1_CLOSE-PUSH_edge_min<0.20",
                "edge_min": em,
                "confidence": vision.get("confidence"),
                "from_action": int(action),
                "to_action": int(flank),
                "reason": "vision softening: edge_min 接近边界, 提前 FLANK 规避 "
                          "(PM Phase B 场景①, 而非死等 dist<0.3)",
            }

        # 场景②: OPPONENT-FOUND + zone == danger -> 线速度 <= 0.45
        if rule_id in self.OPPONENT_FOUND_RULE_IDS and zone == "danger":
            try:
                cur_lin = Action(action).to_cmd()[0]
            except Exception:
                cur_lin = 0.0
            if cur_lin > self.VISION_DANGER_SPEED_CAP:
                return self.VISION_DANGER_SPEED_ACTION, {
                    "applied": True,
                    "scenario": "S2_OPPONENT-FOUND_zone=danger",
                    "zone": zone,
                    "confidence": vision.get("confidence"),
                    "from_action": int(action),
                    "from_speed": round(cur_lin, 3),
                    "to_action": int(self.VISION_DANGER_SPEED_ACTION),
                    "to_speed": round(Action(self.VISION_DANGER_SPEED_ACTION).to_cmd()[0], 3),
                    "reason": "vision softening: zone=danger 降速 (PM Phase B 场景②; "
                              "离散空间无 0.45 档, 保守取 0.38)",
                }
        return action, {}   # 未命中 PM 指定场景 -> 原动作

    def reset(self):
        self.builder.reset()
        self.executor.reset()

    def stats(self) -> dict:
        return {
            "rules_loaded": len(self._rule_policy_map),
            "policies_mapped": len(set(self._rule_policy_map.values())),
        }

    @staticmethod
    def _resolve_params(action_str: str, sensors: dict, metrics: dict) -> dict:
        """Resolve ABDL EXECUTE params from sensor/metric values."""
        import re
        params = {}
        match = re.search(r"\{([^}]+)\}", action_str)
        if not match:
            return params
        inner = match.group(1)
        for m in re.findall(r"'(\w+)':\s*(\w+)\((\w+)\)", inner):
            key, func, var = m
            params[key] = metrics.get(var, sensors.get(var, 0.0))
        for m in re.findall(r"'(\w+)':\s*'(\w+)'", inner):
            params[m[0]] = m[1]
        return params


# ── Quick Test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Test the bridge in isolation
    maker = ABDLDecisionMaker()
    print(f"ABDL Decision Maker loaded:")
    print(f"  Rules: {maker.stats()['rules_loaded']}")
    print(f"  Policies: {maker.stats()['policies_mapped']}")

    # Simulate a world state
    world = {
        "sensors": {
            "edge_proximity": 0.2,
            "opponent_dist": 0.4,
            "opponent_angle": 10.0,
            "opponent_found": True,
            "push_force": 2.0,
            "agent_speed": 0.3,
            "steps_remaining": 150,
            "stuck_counter": 0,
        },
        "metrics": {"opponent_angle": 10.0, "opponent_dist": 0.4},
        "state": {"agent_x": 0.0, "agent_y": 0.0},
        "config": {"arena_size": 2.0},
        "entities": ["opponent_found"],
    }

    action = maker.decide(world)
    action_enum = Action(action)
    cmd = action_enum.to_cmd()
    print(f"\nTest decision:")
    print(f"  World: edge=0.2, opp_dist=0.4, opp_angle=10deg")
    print(f"  Action: {action_enum.name} ({action})")
    print(f"  Cmd: (linear={cmd[0]}, angular={cmd[1]})")

    # Test edge-critical scenario
    world["sensors"]["edge_proximity"] = 0.9
    world["sensors"]["opponent_found"] = False
    action = maker.decide(world)
    action_enum = Action(action)
    print(f"\nEdge-critical test:")
    print(f"  World: edge=0.9")
    print(f"  Action: {action_enum.name} ({action})")
    print(f"  PASS: {action_enum in SAFE_ACTIONS_WHEN_EDGE_CLOSE or action_enum == Action.REV_SLOW}")
