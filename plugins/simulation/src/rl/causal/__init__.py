"""
rl.causal — Causal Inference & Counterfactual Reasoning for BottleSumo.

This module provides three submodules for causal analysis of the robot's
decision-making pipeline:

    scm   — Structural Causal Models (DAG, do-calculus, intervention)
    cate  — Conditional Average Treatment Effect estimation
    cfnet — CounterFactual Network (what-if reasoning for robot actions)

Blueprint alignment:
    Originally marked 🔴 "missing" in architecture audit v9.
    Now filling the L2 capability gap for causal reasoning.
"""

from .scm import StructuralCausalModel, CausalGraph
from .cate import CATEstimator, TreatmentEffect
from .cfnet import CounterFactualNet, CFNetConfig

__all__ = [
    "StructuralCausalModel",
    "CausalGraph",
    "CATEstimator",
    "TreatmentEffect",
    "CounterFactualNet",
    "CFNetConfig",
]
