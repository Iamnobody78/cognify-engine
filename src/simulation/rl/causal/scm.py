"""
scm.py — Structural Causal Model for BottleSumo decision analysis.

Models the causal graph of the robot's perception-action-reward pipeline.
Supports do-calculus interventions and counterfactual queries.

Key causal structure (simplified):
    sensor_data → state_estimate → action → opponent_reaction → reward
                 ↑                                             ↓
                 └─────────── prior_actions ←──────────────────┘

Usage:
    scm = StructuralCausalModel()
    scm.add_edge("sensor_data", "state_estimate")
    scm.add_edge("state_estimate", "action")
    scm.intervene("action", value=3)  # do(action=FORWARD)
    result = scm.query("reward")
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

import numpy as np


@dataclass
class CausalGraph:
    """Directed Acyclic Graph (DAG) for structural causal modeling.

    Nodes represent variables in the robot's decision pipeline.
    Edges represent direct causal relationships.
    """

    nodes: Dict[str, Any] = field(default_factory=dict)
    edges: Set[Tuple[str, str]] = field(default_factory=set)
    parents: Dict[str, Set[str]] = field(default_factory=dict)
    children: Dict[str, Set[str]] = field(default_factory=dict)

    def add_node(self, name: str, value: Any = None) -> None:
        if name not in self.nodes:
            self.nodes[name] = value
            self.parents[name] = set()
            self.children[name] = set()

    def add_edge(self, source: str, target: str) -> None:
        """Add a directed edge source → target."""
        self.add_node(source)
        self.add_node(target)
        self.edges.add((source, target))
        self.parents[target].add(source)
        self.children[source].add(target)
        self._check_acyclic()

    def ancestors(self, node: str) -> Set[str]:
        """All nodes that are ancestors of `node` (including indirect)."""
        result = set()
        stack = list(self.parents.get(node, set()))
        visited = set()
        while stack:
            n = stack.pop()
            if n not in visited:
                visited.add(n)
                result.add(n)
                stack.extend(self.parents.get(n, set()))
        return result

    def descendants(self, node: str) -> Set[str]:
        """All nodes that are descendants of `node`."""
        result = set()
        stack = list(self.children.get(node, set()))
        visited = set()
        while stack:
            n = stack.pop()
            if n not in visited:
                visited.add(n)
                result.add(n)
                stack.extend(self.children.get(n, set()))
        return result

    def backdoor_paths(self, treatment: str, outcome: str) -> List[List[str]]:
        """Find backdoor paths between treatment and outcome (for confounding)."""
        # Simplified: paths that reach treatment via common ancestors of outcome
        outcome_ancestors = self.ancestors(outcome)
        return [
            [t] for t in self.nodes
            if t in outcome_ancestors and (
                (t, treatment) in self.edges or (treatment, t) in self.edges
            )
        ]

    def _check_acyclic(self) -> None:
        """Raise if graph contains cycles (simplified DFS)."""
        visited = set()
        stack = set()

        def dfs(n: str) -> None:
            if n in stack:
                raise ValueError(f"Cycle detected at node '{n}'")
            if n in visited:
                return
            stack.add(n)
            for child in self.children.get(n, set()):
                dfs(child)
            stack.remove(n)
            visited.add(n)

        for node in self.nodes:
            dfs(node)


class StructuralCausalModel:
    """
    SCM for BottleSumo action selection pipeline.

    Models the 5-node causal chain:
        sensor → estimate → action → reaction → reward

    Supports:
    - do-intervention (Pearl's do-calculus)
    - adjustment formula for backdoor confounders
    - counterfactual inference in simplified form
    """

    # BottleSumo canonical causal variables
    CANONICAL_NODES = [
        "sensor_data",       # raw sensor readings (LiDAR, IR, floor)
        "state_estimate",    # fused state (position, velocity, opponent pose)
        "action",            # discrete action 0-10
        "opponent_reaction", # opponent's observed response
        "reward",            # scalar reward signal
    ]

    def __init__(self):
        self.graph = CausalGraph()
        self._structural_eqs: Dict[str, Callable] = {}
        self._frozen: Dict[str, Optional[Any]] = {}
        self._setup_default_graph()

    def _setup_default_graph(self) -> None:
        """Initialize the canonical BottleSumo causal DAG."""
        for node in self.CANONICAL_NODES:
            self.graph.add_node(node)
        edges = [
            ("sensor_data", "state_estimate"),
            ("state_estimate", "action"),
            ("action", "opponent_reaction"),
            ("opponent_reaction", "reward"),
            ("state_estimate", "reward"),       # direct path
            ("prior_action", "state_estimate"),  # temporal feedback (simplified)
        ]
        for s, t in edges:
            self.graph.add_node("prior_action")
            self.graph.add_edge(s, t)

    def add_edge(self, source: str, target: str) -> None:
        self.graph.add_edge(source, target)

    def add_structural_equation(self, node: str, func: Callable) -> None:
        """Register a structural equation f(parents) → node."""
        self._structural_eqs[node] = func

    def intervene(self, node: str, value: Any) -> None:
        """Pearl's do-operator: set variable to value, sever incoming edges.

        do(action = FORWARD) removes all incoming arrows to 'action'.
        """
        self._frozen[node] = value

    def undo_intervention(self, node: str) -> None:
        self._frozen.pop(node, None)

    def query(self, node: str) -> Any:
        """Compute node value under current interventions."""
        if node in self._frozen:
            return self._frozen[node]
        if node in self._structural_eqs:
            parents = self.graph.parents.get(node, set())
            parent_vals = {p: self.query(p) for p in parents}
            return self._structural_eqs[node](parent_vals)
        return self.graph.nodes.get(node)

    def adjust_backdoor(
        self,
        treatment: str,
        outcome: str,
        data: List[Dict[str, Any]],
    ) -> float:
        """Simple backdoor adjustment: average over confounding strata.

        treatment ∈ {0,1}, outcome is continuous.
        """
        confounders = self.graph.backdoor_paths(treatment, outcome)
        # Flatten confounders (simplified)
        conf_set = set()
        for path in confounders:
            conf_set.update(path)
        conf_set.discard(treatment)
        conf_set.discard(outcome)

        if not conf_set or not data:
            return 0.0

        # Stratify by confounder values
        strata: Dict[tuple, List[Dict]] = {}
        for row in data:
            key = tuple(row.get(c) for c in sorted(conf_set))
            strata.setdefault(key, []).append(row)

        ate = 0.0
        for key, rows in strata.items():
            t1 = [r[outcome] for r in rows if r[treatment] == 1]
            t0 = [r[outcome] for r in rows if r[treatment] == 0]
            if t1 and t0:
                ate += (np.mean(t1) - np.mean(t0)) * (len(rows) / len(data))
        return ate

    def counterfactual(
        self,
        observed: Dict[str, Any],
        intervention: Tuple[str, Any],
        target: str,
    ) -> Any:
        """Simplified counterfactual: 'What would reward be if action was different?'

        Args:
            observed: actual observed variable values
            intervention: (node, value) — the do-operation
            target: variable to query under the counterfactual scenario

        Returns:
            Counterfactual value of target variable
        """
        saved = dict(self._frozen)
        self._frozen = {}
        self.intervene(*intervention)

        # Propagate observed non-intervened values
        for var, val in observed.items():
            if var not in self._frozen:
                self.graph.nodes[var] = val

        result = self.query(target)
        self._frozen = saved
        return result

    def causal_effect_bound(
        self,
        treatment: str,
        outcome: str,
        data: List[Dict[str, Any]],
        confidence: float = 0.95,
    ) -> Tuple[float, float]:
        """Estimate a confidence interval for the causal effect."""
        ate = self.adjust_backdoor(treatment, outcome, data)
        if not data:
            return (ate, ate)
        # Bootstrap SE
        n_bootstrap = 200
        bootstrap_ates = []
        n = len(data)
        for _ in range(n_bootstrap):
            idx = np.random.choice(n, n, replace=True)
            sample = [data[i] for i in idx]
            bootstrap_ates.append(self.adjust_backdoor(treatment, outcome, sample))
        se = np.std(bootstrap_ates)
        z = 1.96  # 95% CI
        return (ate - z * se, ate + z * se)


# ── Pre-built BottleSumo SCM ─────────────────────────────────────────

def build_bottlesumo_scm() -> StructuralCausalModel:
    """Return a pre-configured SCM for BottleSumo action selection."""
    scm = StructuralCausalModel()

    # State estimate: linear fusion of sensor data + prior belief
    scm.add_structural_equation(
        "state_estimate",
        lambda p: np.array(p.get("sensor_data", [0])) * 0.8
        + np.array(p.get("prior_action", 0)) * 0.2,
    )

    # Action selection: quantized from continuous preference
    scm.add_structural_equation(
        "action",
        lambda p: int(np.argmax(p.get("state_estimate", [0])[:11]))
        if isinstance(p.get("state_estimate"), (np.ndarray, list))
        else 0,
    )

    return scm
