#!/usr/bin/env python3
"""
V9 Gate Evaluator — BottleSumo Decision Gate.

Runs V9 ABDL rule-driven agent against a suite of opponent strategies
in the lightweight env. Reports winrate vs 60% threshold.

Exit codes:
  0 = PASS  (winrate >= 60%)
  1 = FAIL  (winrate < 60%, triggers plateau_explorer)
  2 = ERROR (infrastructure failure)

Usage:
  python v9_gate_evaluator.py                    # 10 games, default opponents
  python v9_gate_evaluator.py --episodes 20       # custom episode count
  python v9_gate_evaluator.py --ci-check          # CI mode (compact output, exit code)
  python v9_gate_evaluator.py --report            # Full markdown report
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
except ImportError:  # pragma: no cover - optional dep
    yaml = None

# V9 heuristic rule thresholds (externalized 2026-08-05, TASK-005 前置配置化).
# 数值必须与 6d1e5d9 时代完全一致 —— 配置化不改行为。
_HEURISTIC_RULES_DEFAULT: Dict[str, Any] = {
    "l0_safety": {"edge_danger_f": 0.15, "edge_critical": 0.1},
    "l1_tactical": {"opp_detect_dist": 0.5, "opp_angle_tol": 0.3},
    "l2_strategic": {"advance_dist": 0.8},
}

def _load_heuristic_rules() -> Dict[str, Any]:
    """Load heuristic thresholds from heuristic_config.yaml (fallback = defaults).

    行为契约: 返回的数值在配置缺失/损坏时退化为默认值, 保证 V9 门语义不变。
    """
    cfg = _HEURISTIC_RULES_DEFAULT
    if yaml is None:
        return cfg
    p = Path(__file__).resolve().parent / "heuristic_config.yaml"
    try:
        if p.exists():
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            rules = data.get("heuristic_rules", {})
            for section, params in rules.items():
                if isinstance(params, dict):
                    merged = dict(cfg.get(section, {}))
                    merged.update({k: v for k, v in params.items() if k in merged})
                    cfg = {**cfg, section: merged}
    except Exception:  # pragma: no cover - config corruption must not break gate
        pass
    return cfg


def _json_default(o: Any):
    """Make numpy scalars JSON-serializable (reports may contain float32)."""
    try:
        import numpy as np

        if isinstance(o, (np.floating, np.integer)):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
    except ImportError:
        pass
    return str(o)


# Ensure bottlesumo_pi is importable
_here = Path(__file__).resolve().parent.parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

# Project root is parent of bottlesumo_pi/
_PROJECT_ROOT = _here.parent

# ═══════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════

V9_WINRATE_THRESHOLD = 0.60
DEFAULT_EPISODES = 10
MAX_STEPS_PER_EPISODE = 500

# Opponent strategies for the V9 gate
OPPONENT_STRATEGIES = [
    "random",       # pure random actions
    "aggressive",   # always push forward
    "defensive",    # stay near center, react to opponent
    "circler",      # rotate around the ring edge
    "counter",      # wait, then counter-attack
]

GATE_REPORT_PATH = _PROJECT_ROOT / ".aionui" / "meta_governance" / "gate" / "v9_gate_report.json"
PLATEAU_LOG_PATH = _PROJECT_ROOT / ".aionui" / "meta_governance" / "plateau" / "explorer_state.json"


# ═══════════════════════════════════════════════════════════════════════════
# Opponent strategies
# ═══════════════════════════════════════════════════════════════════════════

class OpponentStrategies:
    """Opponent action selectors for the V9 gate."""

    # 21 discrete actions (from wheel_to_discrete.py Action enum)
    # FIXED 2026-08-05: previous constants were WRONG against the real enum —
    # ACTION_REVERSE=12 was TURN_R_HARD (spins right), ACTION_RIGHT=8 was
    # TURN_L_MED (turns LEFT), ACTION_STOP=10 was TURN_R_MILD (spins),
    # ACTION_SPIN=15 was FW_LEFT_HARD (arcs forward-left). All corrected below.
    ACTION_FORWARD = 3       # FW_MED — moderate forward
    ACTION_HARD_FORWARD = 5  # FW_MAX — full forward
    ACTION_REVERSE = 6       # REV_SLOW — moderate reverse
    ACTION_LEFT = 7          # TURN_L_MILD — turn left
    ACTION_RIGHT = 10        # TURN_R_MILD — turn right
    ACTION_STOP = 0          # STOP
    ACTION_SPIN = 9          # TURN_L_HARD — spin

    @staticmethod
    def random(obs: List[float], step: int) -> int:
        """Random action from 0-20."""
        import random
        return random.randint(0, 20)

    @staticmethod
    def aggressive(obs: List[float], step: int) -> int:
        """Always charge forward — steer toward the robot (own-frame obs).

        FIXED 2026-08-05: (a) obs is now in the opponent's own frame (env change),
        (b) deadband was 0.2 DEGREES — so the 'aggressive charger' almost never
        charged, it just turned constantly. 10° deadband mirrors a real charge.
        """
        opp_angle = obs[5] if len(obs) > 5 else 0.0
        if abs(opp_angle) < 10.0:
            return OpponentStrategies.ACTION_HARD_FORWARD
        elif opp_angle < 0:
            # Robot is on our right → turn right toward it
            return OpponentStrategies.ACTION_RIGHT
        else:
            # Robot is on our left → turn left toward it
            return OpponentStrategies.ACTION_LEFT

    @staticmethod
    def defensive(obs: List[float], step: int) -> int:
        """Stay near center, react to opponent approach."""
        edge_f = obs[0] if len(obs) > 0 else 1.0
        opp_dist = obs[4] if len(obs) > 4 else 1.0

        if edge_f < 0.3:  # near edge → back up
            return OpponentStrategies.ACTION_REVERSE
        elif opp_dist < 0.4:  # opponent close → push
            return OpponentStrategies.ACTION_HARD_FORWARD
        else:
            return OpponentStrategies.ACTION_STOP

    @staticmethod
    def circler(obs: List[float], step: int) -> int:
        """Circle around the ring edge."""
        # Alternate between forward-left and forward-right every 20 steps
        # FIXED 2026-08-05: was 4 (FW_FAST, pure forward) and 6 (REV_SLOW,
        # BACKWARD!) — the 'circler' was driving in reverse every other phase.
        phase = (step // 20) % 2
        if phase == 0:
            return 13   # FW_LEFT_MILD — forward + gentle left
        else:
            return 16   # FW_RIGHT_MILD — forward + gentle right

    @staticmethod
    def counter(obs: List[float], step: int) -> int:
        """Wait for opponent to expose flank, then strike."""
        opp_dist = obs[4] if len(obs) > 4 else 1.0
        opp_angle = obs[5] if len(obs) > 5 else 0.0

        if opp_dist < 0.3:
            if abs(opp_angle) > 0.5:
                # Opponent at angle → spin TOWARD it
                # FIXED 2026-08-05: was always ACTION_SPIN (TURN_L_HARD, left-only)
                return 12 if opp_angle < 0 else 9  # TURN_R_HARD / TURN_L_HARD
            else:
                return OpponentStrategies.ACTION_HARD_FORWARD
        elif opp_dist < 0.6:
            return OpponentStrategies.ACTION_STOP  # wait
        else:
            return OpponentStrategies.ACTION_STOP  # wait longer

    @classmethod
    def get(cls, name: str):
        """Get opponent strategy by name."""
        strategies = {
            "random": cls.random,
            "aggressive": cls.aggressive,
            "defensive": cls.defensive,
            "circler": cls.circler,
            "counter": cls.counter,
        }
        return strategies.get(name, cls.random)


# ═══════════════════════════════════════════════════════════════════════════
# V9 Rule Agent
# ═══════════════════════════════════════════════════════════════════════════

class V9RuleAgent:
    """Agent driven by V9 ABDL rules (simulation_rules.abdl)."""

    def __init__(self, force_heuristic: bool = False):
        self._engine = None
        self._policy_executor = None
        self._action_history: List[int] = []
        self._stuck_counter = 0
        self._last_edge_state: Optional[List[float]] = None
        # Measurement honesty: which decision path actually ran.
        # "abdl" = ABDL engine decided; "heuristic" = fallback rules; "mock" = env missing.
        self.mode = "heuristic"
        self._last_heuristic_branch = "init"
        self._force_heuristic = force_heuristic

    def _lazy_init(self):
        """Lazy-load the ABDL engine to avoid import cost on every call."""
        if self._engine is not None:
            return
        if self._force_heuristic:
            print("[!] INFO: --agent heuristic — ABDL disabled, V9 heuristic fallback", file=sys.stderr)
            return
        try:
            from core.meta_language.abdl_action_bridge import (
                WorldStateBuilder,
                ABDLDecisionMaker,
            )
            rules_path = (
                _PROJECT_ROOT / "bottlesumo_pi" / "governance"
                / "meta_language" / "simulation_rules.abdl"
            )
            if not rules_path.exists():
                raise ImportError(f"ABDL rules not found: {rules_path}")
            self._world_builder = WorldStateBuilder()
            self._decision_maker = ABDLDecisionMaker(rules_file=str(rules_path))
            self._engine = self._decision_maker.engine
            self.mode = "abdl"
        except Exception as exc:
            # Honest degradation: ABDL unavailable → heuristic V9 fallback.
            self._engine = None
            self._decision_maker = None
            self._world_builder = None
            print(
                f"[!] WARNING: ABDL engine unavailable ({exc.__class__.__name__}: {exc}) "
                f"— V9 heuristic fallback in use",
                file=sys.stderr,
            )

    def select_action(self, obs: List[float]) -> int:
        """Select action using V9 ABDL rules (with heuristic fallback)."""
        return self.select_action_traced(obs)[0]

    def select_action_traced(self, obs: List[float]) -> Tuple[int, dict]:
        """G3: select_action + return (action, decision_trace).

        Trace exposes mode ("abdl"/"heuristic"), the ABDL rule id + policy that
        fired, or the heuristic branch tag, plus the raw sensor context. This is
        what the RViz debug overlay consumes — "let the rule speak for itself".
        """
        self._lazy_init()
        trace: dict = {
            "mode": self.mode,
            "rule_id": None,
            "policy_id": None,
            "branch": None,
            "reason": "",
            "action": None,
            "sensors": {
                "edge_f": obs[0], "edge_b": obs[1],
                "edge_l": obs[2], "edge_r": obs[3],
                "opp_dist": obs[4], "opp_angle": obs[5],
            },
        }

        if self._engine is not None and self._decision_maker is not None:
            try:
                world_state = self._world_builder.build(obs)
                action, abdl_trace = self._decision_maker.decide_traced(world_state)
                if action is not None:
                    self.mode = "abdl"
                    self._action_history.append(action)
                    trace.update({
                        "mode": "abdl",
                        "rule_id": abdl_trace.get("rule_id"),
                        "policy_id": abdl_trace.get("policy_id"),
                        "reason": abdl_trace.get("reason", ""),
                        "rules_triggered": abdl_trace.get("rules_triggered", []),
                        "action": int(action),
                    })
                    return int(action), trace
            except Exception:
                self.mode = "heuristic"  # fall through to heuristic

        # ── Heuristic V9 fallback ──
        action = self._heuristic_v9(obs)
        trace.update({
            "mode": "heuristic",
            "branch": self._last_heuristic_branch,
            "action": int(action),
            "reason": f"heuristic branch {self._last_heuristic_branch}",
        })
        return int(action), trace

    def _heuristic_v9(self, obs: List[float]) -> int:
        """V9 heuristic rules (simplified from ABDL L0-L2)."""
        rules = _load_heuristic_rules()
        l0 = rules["l0_safety"]
        l1 = rules["l1_tactical"]
        l2 = rules["l2_strategic"]
        edge_danger_f = l0["edge_danger_f"]
        edge_critical = l0["edge_critical"]
        opp_detect_dist = l1["opp_detect_dist"]
        opp_angle_tol = l1["opp_angle_tol"]
        advance_dist = l2["advance_dist"]

        edge_f = obs[0]
        edge_b = obs[1]
        edge_l = obs[2]
        edge_r = obs[3]
        opp_dist = obs[4]
        opp_angle = obs[5]

        # ── L0: Safety rules ──
        # FIXED 2026-08-05: action values were wrong vs Action enum —
        # 'hard reverse'=12 was TURN_R_HARD (spin), 'turn right'=8 was TURN_L_MED
        # (LEFT turn), 'forward-left'=4 was FW_FAST, 'forward-right'=6 was
        # REV_SLOW (BACKWARD!). Corrected to REV_SLOW=6, TURN_R_MILD=10,
        # FW_LEFT_MILD=13, FW_RIGHT_MILD=16.
        # SR-001: edge_danger
        if edge_f < edge_danger_f or any(e < edge_critical for e in [edge_f, edge_b, edge_l, edge_r]):
            # Near any edge → reverse or turn away
            if edge_f < edge_critical:
                self._last_heuristic_branch = "SR-001/edge_f"
                return 6  # REV_SLOW — back away from front edge
            if edge_l < edge_critical:
                self._last_heuristic_branch = "SR-001/edge_l"
                return 10  # TURN_R_MILD — turn away from left edge
            if edge_r < edge_critical:
                self._last_heuristic_branch = "SR-001/edge_r"
                return 7  # TURN_L_MILD — turn away from right edge
            if edge_b < edge_critical:
                self._last_heuristic_branch = "SR-001/edge_b"
                return 5  # FW_MAX — back edge near rim, drive forward

        # ── L1: Tactical rules ──
        # TR-001: opponent_detected
        if opp_dist < opp_detect_dist:
            if abs(opp_angle) < opp_angle_tol:
                # Opponent directly ahead → charge
                self._last_heuristic_branch = "TR-001/charge"
                return 5  # FW_MAX
            elif opp_angle < 0:
                # Opponent on the RIGHT (negative angle) → curve right + forward
                self._last_heuristic_branch = "TR-001/right"
                return 16  # FW_RIGHT_MILD
            else:
                # Opponent on the LEFT (positive angle) → curve left + forward
                self._last_heuristic_branch = "TR-001/left"
                return 13  # FW_LEFT_MILD

        # TR-002: strategic_advance — opponent far
        if opp_dist < advance_dist:
            self._last_heuristic_branch = "TR-002/advance"
            return 3  # moderate forward

        # TR-003: search pattern
        self._last_heuristic_branch = "TR-003/search"
        return 15  # spin to find opponent


# ═══════════════════════════════════════════════════════════════════════════
# Gate Evaluator
# ═══════════════════════════════════════════════════════════════════════════

class V9GateEvaluator:
    """Run V9 rules against opponent suite and evaluate winrate."""

    def __init__(self, episodes: int = DEFAULT_EPISODES, backend: str = "lightweight"):
        self.episodes_per_opponent = max(1, episodes // len(OPPONENT_STRATEGIES))
        self.total_episodes = self.episodes_per_opponent * len(OPPONENT_STRATEGIES)
        self.results: List[Dict[str, Any]] = []
        self.backend = backend  # "lightweight" (kinematic) | "mujoco" (physics)

    # ── Public API ───────────────────────────────────────────────────────

    def evaluate(self, agent_name: str = "abdl") -> Dict[str, Any]:
        """Run full V9 gate evaluation. Returns report dict.

        agent_name: "abdl" (V9 ABDL rules), "heuristic" (canned V9 fallback),
                    "v11" (ported V11 3-phase strategy — control benchmark).
        """
        self.results = []  # reset so repeated evaluate() calls do not accumulate
        agent = self._create_agent(agent_name)
        opponent_factory = OpponentStrategies()

        wins = 0
        total = 0
        strat_results: Dict[str, Dict] = defaultdict(lambda: {"wins": 0, "total": 0, "avg_steps": 0})

        for strat_name in OPPONENT_STRATEGIES:
            opp_strategy = opponent_factory.get(strat_name)

            for ep in range(self.episodes_per_opponent):
                result = self._run_episode(agent, opp_strategy, strat_name, ep)
                self.results.append(result)
                total += 1
                if result["win"]:
                    wins += 1
                strat_results[strat_name]["wins"] += (1 if result["win"] else 0)
                strat_results[strat_name]["total"] += 1
                strat_results[strat_name]["avg_steps"] += result["steps"]

        # Compute per-strategy averages
        for sn in strat_results:
            sr = strat_results[sn]
            if sr["total"] > 0:
                sr["winrate"] = sr["wins"] / sr["total"]
                sr["avg_steps"] /= sr["total"]

        winrate = wins / total if total > 0 else 0.0
        passed = winrate >= V9_WINRATE_THRESHOLD

        report = {
            "gate": "V9",
            "timestamp": time.time(),
            "agent_name": agent_name,
            "threshold": V9_WINRATE_THRESHOLD,
            "total_episodes": total,
            "wins": wins,
            "losses": total - wins,
            "winrate": round(winrate, 4),
            "passed": passed,
            "mode": "mock" if any(r["mode"] == "mock" for r in self.results) else "real",
            "backend": self.backend,
            "agent_mode": agent.mode,
            "strategies": list(OPPONENT_STRATEGIES),
            "per_strategy": {
                sn: {
                    "wins": sr["wins"],
                    "total": sr["total"],
                    "winrate": round(sr["winrate"], 4),
                    "avg_steps": round(sr["avg_steps"], 1),
                }
                for sn, sr in strat_results.items()
            },
            "episode_results": [
                {
                    "episode": r["episode"],
                    "opponent": r["opponent"],
                    "win": r["win"],
                    "steps": r["steps"],
                    "reward": r["reward"],
                    "mode": r["mode"],
                    "agent_mode": r["agent_mode"],
                }
                for r in self.results
            ],
        }

        # Persist
        GATE_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(GATE_REPORT_PATH, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=_json_default)

        # Trigger plateau_explorer if failed
        if not passed:
            self._trigger_plateau_explorer(report)

        return report

    @staticmethod
    def _create_agent(agent_name: str):
        if agent_name == "v11":
            from simulation.v11_agent import V11RuleAgent

            return V11RuleAgent()
        if agent_name == "heuristic":
            return V9RuleAgent(force_heuristic=True)
        return V9RuleAgent()

    @staticmethod
    def _stable_seed(episode_idx: int, opponent_name: str) -> int:
        """Deterministic per-episode seed.

        Python's builtin hash() is salted per-process (PYTHONHASHSEED), which
        silently re-randomizes opponent spawns between runs and breaks A/B
        control comparisons.  Use hashlib so results are reproducible.
        """
        import hashlib

        digest = hashlib.sha256(f"{episode_idx}:{opponent_name}".encode()).hexdigest()
        return int(digest[:8], 16)

    def _run_episode(
        self, agent: V9RuleAgent,
        opponent_fn, opponent_name: str,
        episode_idx: int,
    ) -> Dict[str, Any]:
        """Run a single episode: V9 agent vs opponent."""
        try:
            if self.backend == "mujoco":
                from simulation.mujoco_env import MuJoCoBottleSumoEnv
                env = MuJoCoBottleSumoEnv(opponent_strategy=opponent_fn,
                                          opponent_strategy_name=opponent_name)
            else:
                from simulation.lightweight_env import LightweightBottleSumoEnv
                env = LightweightBottleSumoEnv(opponent_strategy=opponent_fn)
        except ImportError as exc:
            # Fallback: use a minimal mock env
            print(f"[!] WARNING: env backend '{self.backend}' unavailable ({exc}); "
                  f"using MOCK — NOT a real measurement", file=sys.stderr)
            return self._run_mock_episode(agent, opponent_fn, opponent_name, episode_idx)

        obs, _info = env.reset(seed=self._stable_seed(episode_idx, opponent_name))
        total_reward = 0.0
        win = False

        for step in range(MAX_STEPS_PER_EPISODE):
            action = agent.select_action(obs)
            obs, reward, terminated, truncated, info = env.step(action)
            done = terminated or truncated
            total_reward += reward

            if done:
                # Win = terminated episode with win-scale reward (+200 opp out).
                # Timeout (truncated) is never a win, regardless of accumulated reward.
                win = terminated and bool(reward > 5)
                break

        return {
            "episode": episode_idx,
            "opponent": opponent_name,
            "win": win,
            "steps": step + 1,
            "reward": round(total_reward, 2),
            "mode": "real",
            "backend": self.backend,
            "agent_mode": agent.mode,
        }

    def _run_mock_episode(
        self, agent: V9RuleAgent,
        opponent_fn, opponent_name: str,
        episode_idx: int,
    ) -> Dict[str, Any]:
        """Minimal mock episode when lightweight env is unavailable."""
        import random
        random.seed(self._stable_seed(episode_idx, opponent_name))

        print(
            f"[!] WARNING: MOCK MODE — lightweight_env unavailable; "
            f"episode {episode_idx} vs {opponent_name} is NOT a real measurement",
            file=sys.stderr,
        )

        obs = [0.5] * 7
        win = random.random() < 0.35  # ~35% baseline
        steps = random.randint(30, 200)

        return {
            "episode": episode_idx,
            "opponent": opponent_name,
            "win": win,
            "steps": steps,
            "reward": 10.0 if win else -1.0,
            "mode": "mock",
            "agent_mode": agent.mode,
        }

    def _trigger_plateau_explorer(self, report: Dict[str, Any]) -> None:
        """Trigger plateau_explorer self-distillation when gate fails."""
        PLATEAU_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

        state = {
            "triggered_at": time.time(),
            "reason": f"V9 gate winrate {report['winrate']:.1%} < {V9_WINRATE_THRESHOLD:.0%}",
            "gate_report": report,
            "action": "plateau_explorer_self_distillation_queued",
        }

        with open(PLATEAU_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, default=_json_default)

        print(f"\n[!] PLATEAU EXPLORER TRIGGERED: {state['reason']}", file=sys.stderr)


# ═══════════════════════════════════════════════════════════════════════════
# Formatters
# ═══════════════════════════════════════════════════════════════════════════

def format_ci(report: Dict[str, Any]) -> str:
    """Compact CI output."""
    status = "PASS" if report["passed"] else "FAIL"
    return (
        f"V9_GATE: {status} | "
        f"WR={report['winrate']:.1%} ({report['wins']}/{report['total_episodes']}) | "
        f"threshold={report['threshold']:.0%}"
    )


def format_report(report: Dict[str, Any]) -> str:
    """Full markdown report."""
    lines = [
        "# V9 Gate Report",
        "",
        f"**Timestamp**: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(report['timestamp']))}",
        f"**Status**: {'PASS' if report['passed'] else 'FAIL'}",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Winrate | **{report['winrate']:.1%}** |",
        f"| Threshold | {report['threshold']:.0%} |",
        f"| Wins | {report['wins']}/{report['total_episodes']} |",
        f"| Episodes | {report['total_episodes']} |",
        "",
        "## Per-Strategy Breakdown",
        "",
        "| Opponent | Wins | Winrate | Avg Steps |",
        "|----------|------|---------|-----------|",
    ]

    for sn, sr in report["per_strategy"].items():
        lines.append(
            f"| {sn} | {sr['wins']}/{sr['total']} | "
            f"{sr['winrate']:.1%} | {sr['avg_steps']:.0f} |"
        )

    if not report["passed"]:
        lines += [
            "",
            "## Plateau Explorer Triggered",
            "",
            f"Winrate {report['winrate']:.1%} below {report['threshold']:.0%} threshold.",
            "Self-distillation queued. See `.aionui/meta_governance/plateau/explorer_state.json`.",
        ]

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="V9 Gate Evaluator")
    parser.add_argument("--episodes", type=int, default=DEFAULT_EPISODES,
                        help=f"Total episodes (default: {DEFAULT_EPISODES})")
    parser.add_argument("--ci-check", action="store_true",
                        help="CI mode: compact output + exit code")
    parser.add_argument("--report", action="store_true",
                        help="Full markdown report")
    parser.add_argument("--json", action="store_true",
                        help="JSON output to stdout")
    parser.add_argument("--agent", choices=["abdl", "heuristic", "v11"], default="abdl",
                        help="Agent under test: abdl (V9 rules), heuristic (V9 canned), "
                             "v11 (ported V11 strategy — control benchmark)")
    parser.add_argument("--backend", choices=["lightweight", "mujoco"], default="lightweight",
                        help="Simulation backend: lightweight (kinematic 2D) or "
                             "mujoco (rigid-body physics)")
    args = parser.parse_args()

    evaluator = V9GateEvaluator(episodes=args.episodes, backend=args.backend)
    report = evaluator.evaluate(agent_name=args.agent)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=_json_default))
    elif args.ci_check:
        print(format_ci(report))
    elif args.report:
        print(format_report(report))
    else:
        print(format_ci(report))
        print(format_report(report))

    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
