"""
cate.py — Conditional Average Treatment Effect estimation.

Estimates how much changing a specific policy parameter (treatment)
affects win probability (outcome), conditioned on the game state context.

For BottleSumo:
    Treatment:  reward weight coefficient, opponent type, action probability
    Outcome:    win rate, round duration, cumulative reward
    Context:    initial distance, ring proximity, opponent posture

Usage:
    cate = CATEstimator()
    cate.fit(state_features, treatment_indicator, outcomes)
    effect = cate.estimate(feature_vector)
    print(f"ATE: {cate.average_treatment_effect():.3f}")
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


@dataclass
class TreatmentEffect:
    """Result of a CATE estimation query."""
    treatment: str
    outcome: str
    ate: float                          # Average Treatment Effect
    cate: float                         # Conditional ATE (for current context)
    confidence_interval: Tuple[float, float]
    sample_size: int
    context_values: Dict[str, float] = field(default_factory=dict)


class CATEstimator:
    """
    Estimates Conditional Average Treatment Effects for BottleSumo.

    Uses a simplified meta-learner approach (S-learner):
    1. Train a single model on (X, T, Y) where T = treatment indicator
    2. CATE(x) = E[Y|X=x, T=1] - E[Y|X=x, T=0]

    For the BottleSumo use case, this enables questions like:
    - "Does increasing the forward-movement reward in states near the edge
       actually improve win rate?"
    - "How does the opponent type moderate the effect of aggressiveness?"
    """

    def __init__(self, n_bootstrap: int = 500, seed: int = 42):
        self.n_bootstrap = n_bootstrap
        self.rng = np.random.RandomState(seed)
        self._features: Optional[np.ndarray] = None
        self._treatment: Optional[np.ndarray] = None
        self._outcomes: Optional[np.ndarray] = None
        self._is_fit = False

    def fit(
        self,
        features: np.ndarray,      # (N, D) context features
        treatment: np.ndarray,     # (N,) binary treatment indicator
        outcomes: np.ndarray,      # (N,) outcome variable
    ) -> "CATEstimator":
        """Store data for estimation. Assumes pre-collected experiment data."""
        self._features = np.asarray(features, dtype=np.float32)
        self._treatment = np.asarray(treatment, dtype=np.int32).ravel()
        self._outcomes = np.asarray(outcomes, dtype=np.float32).ravel()
        self._is_fit = True
        return self

    def average_treatment_effect(self) -> float:
        """Simple ATE: mean(Y|T=1) - mean(Y|T=0)."""
        if not self._is_fit:
            return 0.0
        t_mask = self._treatment == 1
        return float(np.mean(self._outcomes[t_mask]) - np.mean(self._outcomes[~t_mask]))

    def estimate(
        self,
        context: np.ndarray,
        n_neighbors: int = 30,
    ) -> TreatmentEffect:
        """
        Estimate CATE for a specific context vector using k-NN stratification.

        Args:
            context: (D,) feature vector describing the game state
            n_neighbors: number of nearest neighbors for local estimation

        Returns:
            TreatmentEffect with ATE, CATE, and confidence interval
        """
        if not self._is_fit:
            return TreatmentEffect(
                treatment="unknown", outcome="unknown",
                ate=0.0, cate=0.0,
                confidence_interval=(0.0, 0.0), sample_size=0,
            )

        context = np.asarray(context, dtype=np.float32).ravel()
        distances = np.sqrt(np.sum((self._features - context) ** 2, axis=1))
        nearest_idx = np.argsort(distances)[:n_neighbors]

        local_t = self._treatment[nearest_idx]
        local_y = self._outcomes[nearest_idx]

        t1 = local_y[local_t == 1]
        t0 = local_y[local_t == 0]

        cate_val = float(np.mean(t1) - np.mean(t0)) if len(t1) and len(t0) else 0.0

        # Bootstrap CI for CATE
        bootstrap_cates = []
        n_local = len(nearest_idx)
        for _ in range(self.n_bootstrap):
            idx = self.rng.choice(n_local, n_local, replace=True)
            bt = local_t[idx]
            by = local_y[idx]
            bt1 = by[bt == 1]
            bt0 = by[bt == 0]
            if len(bt1) and len(bt0):
                bootstrap_cates.append(float(np.mean(bt1) - np.mean(bt0)))
        if bootstrap_cates:
            ci = (
                float(np.percentile(bootstrap_cates, 2.5)),
                float(np.percentile(bootstrap_cates, 97.5)),
            )
        else:
            ci = (cate_val, cate_val)

        return TreatmentEffect(
            treatment="treatment",
            outcome="outcome",
            ate=self.average_treatment_effect(),
            cate=cate_val,
            confidence_interval=ci,
            sample_size=len(nearest_idx),
        )

    def estimate_heterogeneity(
        self,
        stratify_by: np.ndarray,  # (N,) categorical variable for stratification
    ) -> Dict[Any, float]:
        """Estimate ATE per stratum to detect heterogeneous treatment effects.

        Useful for: "Does the treatment effect vary by opponent type?"
        """
        if not self._is_fit:
            return {}

        stratify_by = np.asarray(stratify_by).ravel()
        effects = {}
        for stratum in np.unique(stratify_by):
            mask = stratify_by == stratum
            t_mask = mask & (self._treatment == 1)
            c_mask = mask & (self._treatment == 0)
            if np.sum(t_mask) > 0 and np.sum(c_mask) > 0:
                effects[str(stratum)] = float(
                    np.mean(self._outcomes[t_mask]) - np.mean(self._outcomes[c_mask])
                )
        return effects

    def summary(self) -> Dict[str, Any]:
        """Return a summary of the fitted estimator."""
        if not self._is_fit:
            return {"status": "not_fit"}
        n_total = len(self._treatment)
        n_treated = int(np.sum(self._treatment == 1))
        n_control = n_total - n_treated
        return {
            "status": "fit",
            "n_total": n_total,
            "n_treated": n_treated,
            "n_control": n_control,
            "ate": self.average_treatment_effect(),
            "outcome_mean": float(np.mean(self._outcomes)),
            "outcome_std": float(np.std(self._outcomes)),
        }
