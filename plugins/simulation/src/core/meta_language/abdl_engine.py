#!/usr/bin/env python3
"""ABDL Engine — Load, validate, evaluate, and compile Agent Behavior Description Language rules.

ABDL unifies: constitution.yaml + meta_rules.json + core_instruction.md
into a single declarative rule language with 4-level hierarchy.

Capabilities:
  - Load: Parse ABDL YAML files
  - Validate: Check rule consistency, conflicts, completeness
  - Evaluate: Execute condition expressions against a world state
  - Resolve: Find all matching rules for a given state, ordered by priority
  - Compile: Generate Python tier0 scripts from ABDL rules (Phase 2)
"""

import re
import sys
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field


def _log(msg: str) -> None:
    """Runtime diagnostics go to stderr so stdout stays machine-readable (JSON)."""
    print(msg, file=sys.stderr)


# ============================================================================
# Data Types
# ============================================================================

@dataclass
class Rule:
    """A single ABDL rule."""
    id: str
    level: int
    condition: str
    action: str
    priority: int
    description: str = ""
    context: str = ""
    source: str = ""
    depends_on: List[str] = field(default_factory=list)
    conflicts_with: List[str] = field(default_factory=list)
    confidence: float = 1.0
    evidence: str = ""

    @property
    def is_immutable(self) -> bool:
        return self.level == 0

    @property
    def level_name(self) -> str:
        names = {0: "IMMUTABLE_AXIOM", 1: "CONSTITUTIONAL", 2: "OPERATIONAL", 3: "HEURISTIC"}
        return names.get(self.level, "UNKNOWN")

    def __repr__(self):
        return f"Rule({self.id}, L{self.level}, P{self.priority})"


@dataclass
class EvaluationResult:
    """Result of evaluating a rule against a world state."""
    rule: Rule
    triggered: bool
    action: str
    priority: int
    reason: str = ""


# ============================================================================
# Condition Evaluator — Parses and evaluates ABDL condition expressions
# ============================================================================

class ConditionEvaluator:
    """Evaluates ABDL condition expressions against a world state dict."""

    # Token patterns
    SENSOR = re.compile(r"sensor\((\w+)\)")
    METRIC = re.compile(r"metric\((\w+)\)")
    STATE = re.compile(r"state\((\w+)\)")
    CONFIG = re.compile(r"config\((\w+)\)")
    EXISTS = re.compile(r"EXISTS\((\w+)\)")
    BETWEEN = re.compile(r"BETWEEN\(([^,]+),\s*([^,]+),\s*([^)]+)\)")

    def __init__(self, world_state: Dict[str, Any]):
        self.state = world_state

    def evaluate(self, condition: str) -> Tuple[bool, str]:
        """Evaluate a condition expression. Returns (result, reason)."""
        try:
            # Replace ABDL function calls with their values
            # NOTE: _resolve_between MUST run BEFORE _resolve_sensor —
            # BETWEEN(sensor(x), lo, hi) needs its inner sensor(x) intact
            # so _repl can resolve it; if sensor is replaced first, the
            # expression becomes BETWEEN(0.2, 0.4, 0.6) and the outer
            # "sensor(x)" copy left behind yields "0.2 False" SyntaxError.
            resolved = condition
            resolved = self._resolve_between(resolved)
            resolved = self._resolve_sensor(resolved)
            resolved = self._resolve_metric(resolved)
            resolved = self._resolve_state(resolved)
            resolved = self._resolve_config(resolved)
            resolved = self._resolve_exists(resolved)
            resolved = self._resolve_between(resolved)
            resolved = self._resolve_operators(resolved)

            # Now it should be a simple Python boolean expression
            # Safety: only evaluate if it passes basic safety checks
            if not self._is_safe(resolved):
                return False, f"Unsafe expression: {resolved}"

            result = eval(resolved, {"__builtins__": {}}, {})
            return bool(result), f"Evaluated: {condition} -> {resolved} = {result}"
        except Exception as e:
            return False, f"Evaluation error: {e}"

    def _resolve_sensor(self, expr: str) -> str:
        for m in self.SENSOR.findall(expr):
            val = self.state.get("sensors", {}).get(m, 0)
            expr = expr.replace(f"sensor({m})", repr(val))
        return expr

    def _resolve_metric(self, expr: str) -> str:
        for m in self.METRIC.findall(expr):
            val = self.state.get("metrics", {}).get(m, 0)
            expr = expr.replace(f"metric({m})", repr(val))
        return expr

    def _resolve_state(self, expr: str) -> str:
        for m in self.STATE.findall(expr):
            val = self.state.get("state", {}).get(m, None)
            expr = expr.replace(f"state({m})", repr(val))
        return expr

    def _resolve_config(self, expr: str) -> str:
        for m in self.CONFIG.findall(expr):
            val = self.state.get("config", {}).get(m, 0)
            expr = expr.replace(f"config({m})", repr(val))
        return expr

    def _resolve_exists(self, expr: str) -> str:
        for m in self.EXISTS.findall(expr):
            # Check if entity exists in any part of world state
            found = (
                m in self.state.get("sensors", {})
                or m in self.state.get("metrics", {})
                or m in self.state.get("state", {})
                or m in self.state.get("config", {})
                or m in self.state.get("entities", [])
            )
            expr = expr.replace(f"EXISTS({m})", str(found))
        return expr

    def _resolve_between(self, expr: str) -> str:
        # FIXED 2026-08-05 (queue #4 root cause): the old code rebuilt the
        # BETWEEN(...) match with a no-space key (f"BETWEEN({val_str},{lo_str},{hi_str})")
        # while the original text contains spaces (", -12, 12") -> replace() never
        # matched -> BETWEEN(...) leaked into eval -> SyntaxError -> every BETWEEN
        # rule permanently False. That silently disabled SIM-ADVANCED-CLOSE-PUSH
        # (max-speed push) etc. Use re.sub with the ORIGINAL matched text instead.
        def _repl(m):
            val_str, lo_str, hi_str = m.group(1), m.group(2), m.group(3)
            resolved_val = self._resolve_sensor(val_str.strip())
            resolved_val = self._resolve_metric(resolved_val)
            try:
                val = eval(resolved_val, {"__builtins__": {}}, {})
                lo = float(lo_str.strip())
                hi = float(hi_str.strip())
                return str(lo <= val <= hi)
            except Exception:
                return "False"

        return self.BETWEEN.sub(_repl, expr)

    def _resolve_operators(self, expr: str) -> str:
        """Resolve ABDL AND/OR/NOT to Python and/or/not."""
        expr = expr.replace(" AND ", " and ")
        expr = expr.replace(" OR ", " or ")
        expr = expr.replace("NOT(", "not (")
        return expr

    def _is_safe(self, expr: str) -> bool:
        """Basic safety check — reject expressions with dangerous constructs."""
        dangerous = ["__", "import", "exec", "open", "os.", "sys.", "subprocess",
                     "lambda", "class ", "def "]
        return not any(d in expr.lower() for d in dangerous)


# ============================================================================
# ABDL Engine — Full lifecycle management
# ============================================================================

class ABDLEngine:
    """Loads, validates, evaluates, and manages ABDL rules.

    This is the single source of truth for all agent behavior rules.
    """

    def __init__(self, project_root: str = "."):
        self.root = Path(project_root)
        self.rules_file = self.root / "governance" / "meta_language" / "system_rules.abdl"
        self.schema_file = self.root / "governance" / "meta_language" / "abdl_schema.yaml"
        self.rules: Dict[str, Rule] = {}
        self.loaded = False
        self.validation_errors: List[str] = []

    # ── Loading ──

    def load(self) -> bool:
        """Load all ABDL rules from system_rules.abdl."""
        if not self.rules_file.exists():
            _log(f"[ERROR] Rules file not found: {self.rules_file}")
            return False

        with open(self.rules_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        for rule_data in data.get("rules", []):
            rule = Rule(
                id=rule_data["id"],
                level=rule_data["level"],
                condition=rule_data["condition"],
                action=rule_data["action"],
                priority=rule_data["priority"],
                description=rule_data.get("description", ""),
                context=rule_data.get("context", ""),
                source=rule_data.get("source", ""),
                depends_on=rule_data.get("depends_on", []),
                conflicts_with=rule_data.get("conflicts_with", []),
                confidence=rule_data.get("confidence", 1.0),
                evidence=rule_data.get("evidence", ""),
            )
            self.rules[rule.id] = rule

        self.loaded = True
        _log(f"[OK] ABDL loaded: {len(self.rules)} rules ({self._count_by_level()})")
        return True

    def _count_by_level(self) -> str:
        counts = {0: 0, 1: 0, 2: 0, 3: 0}
        for r in self.rules.values():
            counts[r.level] = counts.get(r.level, 0) + 1
        return f"L0={counts[0]}, L1={counts[1]}, L2={counts[2]}, L3={counts[3]}"

    # ── Querying ──

    def get_rule(self, rule_id: str) -> Optional[Rule]:
        return self.rules.get(rule_id)

    def get_rules_by_level(self, level: int) -> List[Rule]:
        return sorted(
            [r for r in self.rules.values() if r.level == level],
            key=lambda r: -r.priority
        )

    def get_rules_by_context(self, context: str) -> List[Rule]:
        return [r for r in self.rules.values() if r.context == context]

    def get_immutable_axioms(self) -> List[Rule]:
        return self.get_rules_by_level(0)

    # ── Evaluation ──

    def evaluate(self, world_state: Dict[str, Any]) -> List[EvaluationResult]:
        """Evaluate all rules against a world state. Returns triggered rules sorted by priority."""
        evaluator = ConditionEvaluator(world_state)
        results = []

        for rule in self.rules.values():
            triggered, reason = evaluator.evaluate(rule.condition)
            if triggered:
                results.append(EvaluationResult(
                    rule=rule,
                    triggered=True,
                    action=rule.action,
                    priority=rule.priority,
                    reason=reason,
                ))

        # Sort by priority (highest first)
        results.sort(key=lambda r: -r.priority)
        return results

    def resolve(self, world_state: Dict[str, Any]) -> List[Dict]:
        """Resolve: find all triggered actions for a given world state.
        Returns ordered list of actions with their triggering rules.
        """
        triggered = self.evaluate(world_state)
        return [
            {
                "action": r.action,
                "rule_id": r.rule.id,
                "level": r.rule.level,
                "priority": r.rule.priority,
                "reason": r.reason,
            }
            for r in triggered
        ]

    def get_top_action(self, world_state: Dict[str, Any]) -> Optional[Dict]:
        """Get the single highest-priority action for a given state."""
        triggered = self.evaluate(world_state)
        if not triggered:
            return None
        top = triggered[0]
        return {
            "action": top.action,
            "rule_id": top.rule.id,
            "priority": top.rule.priority,
        }

    # ── Validation ──

    def validate(self) -> Tuple[bool, List[str]]:
        """Validate all rules for consistency. Returns (valid, errors)."""
        errors = []

        # Check unique IDs
        ids = list(self.rules.keys())
        if len(ids) != len(set(ids)):
            errors.append("Duplicate rule IDs detected")

        # Check level-0 rules don't conflict
        l0_rules = self.get_rules_by_level(0)
        for i, r1 in enumerate(l0_rules):
            for r2 in l0_rules[i + 1:]:
                if r1.conflicts_with and r2.id in r1.conflicts_with:
                    errors.append(f"LEVEL 0 CONFLICT: {r1.id} <-> {r2.id}")

        # Check dependency references exist
        for rule in self.rules.values():
            for dep_id in rule.depends_on:
                if dep_id not in self.rules:
                    errors.append(f"Rule {rule.id} depends on non-existent {dep_id}")

        # Check confidence thresholds
        for rule in self.rules.values():
            if rule.confidence < 0.5:
                errors.append(f"Rule {rule.id} has low confidence ({rule.confidence}) with no fallback")

        # Check that L2+ rules don't override L0 rules
        l0_ids = {r.id for r in l0_rules}
        for rule in self.rules.values():
            if rule.level >= 2:
                for conflict_id in rule.conflicts_with:
                    if conflict_id in l0_ids:
                        errors.append(f"ILLEGAL: L{rule.level} rule {rule.id} conflicts with L0 rule {conflict_id}")

        self.validation_errors = errors
        return len(errors) == 0, errors

    # ── Modification (self-modification) ──

    def modify_rule(self, rule_id: str, updates: Dict[str, Any]) -> bool:
        """Modify a rule's parameters. Level-0 rules require human confirmation."""
        rule = self.rules.get(rule_id)
        if not rule:
            return False

        if rule.level == 0:
            _log(f"[BLOCKED] Cannot modify immutable axiom {rule_id} without human confirmation")
            return False

        for key, value in updates.items():
            if hasattr(rule, key):
                setattr(rule, key, value)

        _log(f"[OK] Modified rule {rule_id}: {updates}")
        return True

    def add_rule(self, rule_data: Dict) -> bool:
        """Add a new rule. Cannot add at level 0 without human confirmation."""
        if rule_data.get("level") == 0:
            _log("[BLOCKED] Cannot add level-0 rules without human confirmation")
            return False

        rule_id = rule_data["id"]
        if rule_id in self.rules:
            _log(f"[ERROR] Rule {rule_id} already exists")
            return False

        rule = Rule(
            id=rule_id,
            level=rule_data["level"],
            condition=rule_data["condition"],
            action=rule_data["action"],
            priority=rule_data.get("priority", 50),
            description=rule_data.get("description", ""),
            context=rule_data.get("context", ""),
            confidence=rule_data.get("confidence", 1.0),
        )
        self.rules[rule.id] = rule
        _log(f"[OK] Added rule {rule_id} at level {rule.level}")
        return True

    def save(self) -> bool:
        """Persist current rules back to system_rules.abdl."""
        data = {
            "version": "1.0",
            "generated": datetime.now().isoformat(),
            "total_rules": len(self.rules),
            "rules": [
                {
                    "id": r.id,
                    "level": r.level,
                    "condition": r.condition,
                    "action": r.action,
                    "priority": r.priority,
                    "description": r.description,
                    "context": r.context,
                    "source": r.source,
                    "depends_on": r.depends_on,
                    "conflicts_with": r.conflicts_with,
                    "confidence": r.confidence,
                    "evidence": r.evidence,
                }
                for r in sorted(self.rules.values(), key=lambda r: (r.level, -r.priority))
            ],
        }
        with open(self.rules_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        _log(f"[OK] Saved {len(self.rules)} rules to {self.rules_file}")
        return True

    # ── Reporting ──

    def report(self) -> str:
        """Generate a human-readable rule system report."""
        if not self.loaded:
            return "ABDL Engine not loaded."

        valid, errors = self.validate()
        status = "[VALID]" if valid else f"[{len(errors)} ERRORS]"

        report = f"""# ABDL Rule System Report
Generated: {datetime.now().isoformat()}
Status: {status}

## Rule Count
- Level 0 (Immutable): {len(self.get_rules_by_level(0))}
- Level 1 (Constitutional): {len(self.get_rules_by_level(1))}
- Level 2 (Operational): {len(self.get_rules_by_level(2))}
- Level 3 (Heuristic): {len(self.get_rules_by_level(3))}
- Total: {len(self.rules)}

## Immutable Axioms
"""
        for r in self.get_immutable_axioms():
            report += f"- **{r.id}** (P{r.priority}): {r.description}\n"

        if errors:
            report += f"\n## Validation Errors\n"
            for e in errors:
                report += f"- {e}\n"

        report += f"\n## Context Coverage\n"
        contexts = {}
        for r in self.rules.values():
            contexts[r.context] = contexts.get(r.context, 0) + 1
        for ctx, count in sorted(contexts.items()):
            report += f"- {ctx}: {count} rules\n"

        return report


# ============================================================================
# Self-Test
# ============================================================================

def main():
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else "."

    engine = ABDLEngine(root)
    if not engine.load():
        sys.exit(1)

    # Validation
    valid, errors = engine.validate()
    status = "[OK] All rules valid" if valid else f"[WARN] {len(errors)} validation errors"
    print(f"\nValidation: {status}")
    for e in errors:
        print(f"  - {e}")

    # Test: evaluate against simulated world states
    print("\n" + "=" * 60)
    print("SCENARIO TESTS")

    # Scenario 1: Dangerous decision
    state1 = {
        "state": {"system_status": "running"},
        "metrics": {"consecutive_wr_drops": 4, "confirmed_rounds": 2},
    }
    results1 = engine.evaluate(state1)
    print(f"\nScenario 1: WR drops + unsafe promotion")
    for r in results1[:3]:
        print(f"  [L{r.rule.level}] {r.rule.id}: {r.action[:60]}")

    # Scenario 2: Edge detection
    state2 = {
        "sensors": {"min_edge_distance": 0.15, "opponent_distance": 0.8},
    }
    results2 = engine.evaluate(state2)
    print(f"\nScenario 2: Near edge")
    for r in results2[:3]:
        print(f"  [L{r.rule.level}] {r.rule.id}: {r.action[:60]}")

    # Scenario 3: Budget exceeded
    state3 = {
        "config": {"daily_cost": 6.50, "budget_limit": 5.0},
    }
    results3 = engine.evaluate(state3)
    print(f"\nScenario 3: Budget exceeded")
    for r in results3[:3]:
        print(f"  [L{r.rule.level}] {r.rule.id}: {r.action[:60]}")

    # Scenario 4: Normal operation
    state4 = {
        "sensors": {
            "min_edge_distance": 1.0,
            "opponent_distance": 2.0,
            "agent_heartbeat_gap": 5,
        },
        "metrics": {"consecutive_wr_drops": 0, "candidates_count": 30},
        "state": {"system_status": "running", "firmware_modified": False},
        "config": {"daily_cost": 0.50, "budget_limit": 5.0},
    }
    results4 = engine.evaluate(state4)
    print(f"\nScenario 4: Normal operation")
    for r in results4[:3]:
        print(f"  [L{r.rule.level}] {r.rule.id}: {r.action[:60]}")

    print("\n" + "=" * 60)
    print("[OK] ABDL Engine self-test complete")


if __name__ == "__main__":
    main()
