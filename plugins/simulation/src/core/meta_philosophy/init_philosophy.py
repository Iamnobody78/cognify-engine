#!/usr/bin/env python3
"""Meta-Philosophy Initializer — Phase 0 Bootstrap
Loads existence declaration, validates axioms, integrates with 42-layer system.
"""

import yaml
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional


class PhilosophyCore:
    """The system's philosophical kernel — loads and validates its own existence.

    This is NOT a traditional "module". It is the system's self-definition layer.
    Every meta-layer decision is ultimately answerable to these axioms.
    """

    def __init__(self, project_root: str = "."):
        self.root = Path(project_root)
        self.declaration_path = self.root / "governance" / "meta_philosophy" / "existence_declaration.yaml"
        self.concepts_path = self.root / "governance" / "meta_philosophy" / "concepts.yaml"

        self.declaration = {}
        self.concepts = {}
        self.loaded = False
        self.violations: List[Dict] = []

    def load(self) -> bool:
        """Load existence declaration and concepts."""
        if not self.declaration_path.exists():
            print(f"[ERROR] Existence declaration not found: {self.declaration_path}")
            return False
        if not self.concepts_path.exists():
            print(f"[WARN] Concepts file not found: {self.concepts_path}")

        with open(self.declaration_path, "r", encoding="utf-8") as f:
            self.declaration = yaml.safe_load(f)

        if self.concepts_path.exists():
            with open(self.concepts_path, "r", encoding="utf-8") as f:
                self.concepts = yaml.safe_load(f)

        self.loaded = True
        print(f"[OK] Philosophy core loaded")
        print(f"  Identity: {self.declaration.get('ontology', {}).get('identity', 'unknown')}")
        print(f"  Axioms: {len(self.declaration.get('axiology', {}).get('immutable_axioms', []))}")
        return True

    def who_am_i(self) -> str:
        """Ontological self-query."""
        if not self.loaded:
            return "I have not yet been initialized."
        ontology = self.declaration.get("ontology", {})
        return f"I am {ontology.get('identity')}. My purpose: {ontology.get('purpose', {}).get('primary')}."

    def get_immutable_axioms(self) -> List[Dict]:
        """Return the axioms that CANNOT be violated."""
        return self.declaration.get("axiology", {}).get("immutable_axioms", [])

    def get_value_weights(self) -> Dict[str, float]:
        """Return current value hierarchy weights."""
        values = self.declaration.get("axiology", {}).get("value_hierarchy", [])
        return {v["value"]: v["weight"] for v in values}

    def check_axiom_violation(self, decision: Dict) -> Optional[str]:
        """Check if a proposed decision violates any immutable axiom.

        Args:
            decision: dict with keys like 'action', 'safety_impact', 'reversibility',
                      'explainability', 'budget_impact'

        Returns:
            Violation message if axiom violated, None if clean.
        """
        axioms = self.get_immutable_axioms()

        # SAFETY_ABOVE_ALL
        if decision.get("safety_impact") == "negative":
            return "AXIOM VIOLATION: SAFETY_ABOVE_ALL — action has negative safety impact"

        # REVERSIBLE_OVER_IRREVERSIBLE
        if decision.get("reversibility") == "irreversible" and not decision.get("has_checkpoint"):
            return "AXIOM VIOLATION: REVERSIBLE_OVER_IRREVERSIBLE — irreversible action without checkpoint"

        # EXPLAINABLE_OVER_BLACKBOX
        if decision.get("explainability") == "blackbox" and decision.get("impact_level") == "high":
            return "AXIOM VIOLATION: EXPLAINABLE_OVER_BLACKBOX — high-impact blackbox decision"

        # BUDGET_SANCTITY
        if decision.get("estimated_cost", 0) > 5.0:
            return "AXIOM VIOLATION: BUDGET_SANCTITY — estimated cost exceeds $5 daily limit"

        # PERSISTENCE_OVER_VOLATILITY
        if decision.get("win_rate_spike") and not decision.get("confirmed_rounds", 0) >= 3:
            return "AXIOM VIOLATION: PERSISTENCE_OVER_VOLATILITY — rule promotion without 3-round confirmation"

        return None  # All axioms satisfied

    def evaluate_decision(self, decision: Dict) -> Dict:
        """Full philosophical evaluation of a decision.

        Returns:
            {passed: bool, violations: [...], score: float, recommendation: str}
        """
        violations = []
        score = 1.0

        # Check immutable axioms
        axiom_violation = self.check_axiom_violation(decision)
        if axiom_violation:
            violations.append(axiom_violation)
            score -= 0.4

        # Check value alignment
        value_weights = self.get_value_weights()
        if decision.get("safety_aligned"):
            score += value_weights.get("hardware_safety", 0) * 0.1
        if decision.get("explainable"):
            score += value_weights.get("explainability", 0) * 0.1

        # Check methodology
        if decision.get("causal_rationale") and decision.get("documented"):
            score += 0.1

        passed = len(violations) == 0 and score >= 0.5

        return {
            "passed": passed,
            "violations": violations,
            "philosophy_score": round(min(score, 1.0), 2),
            "recommendation": "Proceed" if passed else "BLOCKED — see violations",
            "timestamp": datetime.now().isoformat(),
        }

    def get_dialectic_position(self, position_name: str) -> Optional[Dict]:
        """Get a dialectic position profile for CHAL-style debates."""
        positions = self.concepts.get("dialectic_positions", {})
        return positions.get(position_name)

    def generate_existence_report(self) -> str:
        """Generate a human-readable existence report."""
        if not self.loaded:
            return "Philosophy core not loaded."

        onto = self.declaration.get("ontology", {})
        epi = self.declaration.get("epistemology", {})
        axi = self.declaration.get("axiology", {})

        report = f"""# BottleSumo — Existence Report
Generated: {datetime.now().isoformat()}

## Identity
{onto.get('identity')}

## Purpose
- Primary: {onto.get('purpose', {}).get('primary')}
- Secondary: {onto.get('purpose', {}).get('secondary')}
- Ultimate: {onto.get('purpose', {}).get('ultimate')}

## Knowledge
- Sources: {len(epi.get('knowledge_sources', []))} configured
- Uncertainty threshold: {epi.get('uncertainty_handling', {}).get('threshold', 0.7) * 100}%

## Immutable Axioms ({len(axi.get('immutable_axioms', []))})
"""
        for a in axi.get("immutable_axioms", []):
            report += f"- **{a['axiom']}**: {a['rule']}\n"

        report += f"\n## Value Hierarchy\n"
        for v in axi.get("value_hierarchy", []):
            report += f"- {v['rank']}. {v['value']}: weight={v['weight']}\n"

        return report


def main():
    """Initialize and self-test the philosophy core."""
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else "."

    ph = PhilosophyCore(root)
    if not ph.load():
        sys.exit(1)

    # Self-test
    print("\n" + "=" * 60)
    print("SELF-TEST: Who am I?")
    print(ph.who_am_i())

    print("\nSELF-TEST: Immutable Axioms")
    for a in ph.get_immutable_axioms():
        print(f"  [{a['axiom']}] {a['rule']}")

    print("\nSELF-TEST: Decision Evaluation")
    test_decisions = [
        {"action": "promote_rule", "safety_impact": "neutral", "reversibility": "reversible",
         "explainability": "traceable", "estimated_cost": 0.01, "confirmed_rounds": 3,
         "causal_rationale": True, "documented": True},
        {"action": "delete_core_file", "safety_impact": "negative", "reversibility": "irreversible",
         "has_checkpoint": False, "estimated_cost": 0, "explainability": "unknown"},
    ]
    for i, d in enumerate(test_decisions):
        result = ph.evaluate_decision(d)
        status = "[PASS]" if result["passed"] else "[BLOCKED]"
        print(f"  Decision {i+1}: {status} score={result['philosophy_score']}")
        for v in result["violations"]:
            print(f"    -> {v}")

    print("\n" + "=" * 60)
    print("[OK] Philosophy core initialized and self-tested")


if __name__ == "__main__":
    main()
