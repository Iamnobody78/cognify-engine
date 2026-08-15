"""RealityBridge: P1 external world feedback alignment engine.

Orchestrates 4 adapters + cache + gap analysis to provide a single
API for the meta-governance layer to query real-world signals.

Quick start:
    bridge = RealityBridge()
    bridge.open()

    # Adapter 1: inject simulation samples
    sim = SimulationAdapter(env)
    sim.on_sample(bridge.on_sample)

    # Adapter 2: parse training logs
    bridge.ingest_training_logs("logs/")

    # Adapter 3: parse user feedback
    bridge.ingest_feedback("feedback/annotations.json")

    # Adapter 4: parse shadow loop history
    bridge.ingest_shadow_loop("shadow_loop/versions/")

    # Query and analyze
    stats = bridge.stats(Channel.TRAINING_LOG)
    gap = bridge.detect_gap()

    bridge.close()
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .adapters import (
    ShadowLoopAdapter,
    SimulationAdapter,
    TrainingLogAdapter,
    UserFeedbackAdapter,
)
from .cache import RealityCache
from .models import (
    Channel,
    GapReport,
    RealitySample,
    Severity,
)


class RealityBridge:
    """Central orchestrator for all reality feedback channels."""

    def __init__(self, db_path: Optional[Path] = None):
        self._cache = RealityCache(db_path)
        self._sim_adapter: Optional[SimulationAdapter] = None
        self._training_adapter = TrainingLogAdapter()
        self._feedback_adapter = UserFeedbackAdapter()
        self._shadow_adapter = ShadowLoopAdapter()

        self._sample_count: Dict[Channel, int] = {
            ch: 0 for ch in Channel
        }
        self._listeners: List[Callable[[RealitySample], None]] = []

    # ── Lifecycle ───────────────────────────────────────────────────────

    def open(self) -> RealityBridge:
        """Open the cache and return self for chaining."""
        self._cache.open()
        return self

    def close(self) -> None:
        self._cache.close()

    def __enter__(self):
        return self.open()

    def __exit__(self, *args):
        self.close()

    # ── Sample injection (real-time callbacks) ──────────────────────────

    def on_sample(self, sample: RealitySample) -> None:
        """Callback for real-time sample injection (from SimulationAdapter)."""
        self._sample_count[sample.channel] += 1
        self._cache.insert(sample)
        for listener in self._listeners:
            try:
                listener(sample)
            except Exception:
                pass

    def add_listener(self, callback: Callable[[RealitySample], None]) -> None:
        """Register a listener for all incoming RealitySamples."""
        self._listeners.append(callback)

    # ── Batch ingestion ─────────────────────────────────────────────────

    def ingest_training_logs(self, path: str, pattern: str = "*.csv") -> int:
        """Parse training logs from a directory and store in cache.

        Returns: number of samples ingested.
        """
        dir_path = Path(path)
        if not dir_path.exists():
            return 0

        samples = self._training_adapter.parse_directory(dir_path, pattern)
        return self._cache.insert_many(samples)

    def ingest_feedback(self, path: str) -> int:
        """Parse user feedback files and store in cache.

        Supports: .json, .yaml, .txt, .md (conversation logs)
        Returns: number of samples ingested.
        """
        fp = Path(path)
        if not fp.exists():
            return 0

        if fp.is_file():
            samples = self._feedback_adapter.parse_file(fp)
            return self._cache.insert_many(samples)

        # Directory: parse all feedback files
        total = 0
        for child in fp.iterdir():
            if child.suffix in (".json", ".yaml", ".yml", ".txt", ".md"):
                samples = self._feedback_adapter.parse_file(child)
                total += self._cache.insert_many(samples)
        return total

    def ingest_shadow_loop(self, path: str) -> int:
        """Parse shadow loop artifacts and store in cache.

        Supports: version snapshots, gate history, rule evolution logs.
        Returns: number of samples ingested.
        """
        dir_path = Path(path)
        if not dir_path.exists():
            return 0

        total = 0

        # Version snapshots
        for fp in sorted(dir_path.glob("version_*.json")):
            samples = self._shadow_adapter.parse_version_snapshot(fp)
            total += self._cache.insert_many(samples)

        # Gate history
        gate_fp = dir_path / "gate_history.json"
        if gate_fp.exists():
            samples = self._shadow_adapter.parse_gate_history(gate_fp)
            total += self._cache.insert_many(samples)

        # Rule evolution
        rule_fp = dir_path / "rule_evolution.json"
        if rule_fp.exists():
            samples = self._shadow_adapter.parse_rule_evolution(rule_fp)
            total += self._cache.insert_many(samples)

        # Also try CSV variants
        for fp in dir_path.glob("*.csv"):
            samples = self._shadow_adapter.parse_rule_evolution(fp)
            total += self._cache.insert_many(samples)

        return total

    # ── Query ───────────────────────────────────────────────────────────

    def query(
        self,
        channel: Optional[Channel] = None,
        since: Optional[float] = None,
        until: Optional[float] = None,
        tag: Optional[str] = None,
        limit: int = 1000,
    ) -> List[RealitySample]:
        """Query samples from the cache."""
        return self._cache.query(
            channel=channel, since=since, until=until,
            tag=tag, limit=limit,
        )

    def stats(self, channel: Optional[Channel] = None) -> Dict[str, Any]:
        """Aggregate statistics for a channel (or all channels)."""
        return self._cache.stats(channel=channel)

    def total_samples(self, channel: Optional[Channel] = None) -> int:
        """Total samples stored in cache."""
        return self._cache.total_count(channel)

    # ── Gap Analysis ────────────────────────────────────────────────────

    def detect_gap(self) -> GapReport:
        """Analyze perception-reality gaps across all 4 channels.

        The perception-reality gap is the delta between what the
        meta-theory expects and what the world actually produces.

        Returns:
            GapReport with per-channel scores and aggregate severity.
        """
        now = time.time()
        sim_stats = self._cache.stats(Channel.SIMULATION)
        train_stats = self._cache.stats(Channel.TRAINING_LOG)
        fb_stats = self._cache.stats(Channel.USER_FEEDBACK)
        shadow_stats = self._cache.stats(Channel.SHADOW_LOOP)

        # ── Simulation gap: expected 47%+ winrate baseline ──
        sim_winrate = sim_stats.get("winrate", 0.0)
        sim_total = sim_stats.get("total_samples", 0)
        if sim_total == 0:
            sim_gap = 0.0  # no data → no gap
        else:
            expected_winrate = 0.47  # V9 NN baseline
            sim_gap = max(0.0, expected_winrate - sim_winrate) / expected_winrate

        # ── Training gap: loss should be decreasing ──
        train_samples = self._cache.query(
            channel=Channel.TRAINING_LOG, limit=500,
        )
        train_gap = self._compute_training_gap(train_samples)

        # ── User feedback gap: corrections vs confidence ──
        fb_samples = self._cache.query(
            channel=Channel.USER_FEEDBACK, limit=500,
        )
        fb_gap = self._compute_feedback_gap(fb_samples)

        # ── Shadow loop gap: winrate trend should be monotonically increasing ──
        shadow_samples = self._cache.query(
            channel=Channel.SHADOW_LOOP, limit=500,
        )
        shadow_metrics = self._shadow_adapter.compute_evolution_metrics(
            shadow_samples,
        )
        shadow_gap = self._compute_shadow_gap(shadow_metrics)

        # ── Weighted aggregate (P0 channels get higher weight) ──
        overall_gap = (
            0.35 * sim_gap +
            0.30 * train_gap +
            0.20 * fb_gap +
            0.15 * shadow_gap
        )

        severity = self._classify_severity(overall_gap)

        report = GapReport(
            generated_at=now,
            simulation_gap=round(sim_gap, 4),
            training_gap=round(train_gap, 4),
            user_feedback_gap=round(fb_gap, 4),
            shadow_loop_gap=round(shadow_gap, 4),
            overall_gap=round(overall_gap, 4),
            severity=severity,
            detail=self._format_detail(sim_gap, train_gap, fb_gap, shadow_gap),
        )

        self._cache.save_gap_report(report)
        return report

    def latest_gap(self) -> Optional[Dict]:
        """Return the most recent gap analysis."""
        return self._cache.latest_gap_report()

    # ── Convenience: full pipeline ──────────────────────────────────────

    def report(self) -> Dict[str, Any]:
        """Generate a comprehensive reality bridge status report."""
        gap = self.detect_gap()

        return {
            "gap_report": gap.to_dict(),
            "channel_stats": {
                "simulation": self._cache.stats(Channel.SIMULATION),
                "training_log": self._cache.stats(Channel.TRAINING_LOG),
                "user_feedback": self._cache.stats(Channel.USER_FEEDBACK),
                "shadow_loop": self._cache.stats(Channel.SHADOW_LOOP),
            },
            "total_samples": {
                ch.value: self._cache.total_count(ch)
                for ch in Channel
            },
            "aggregated_feedback": {
                scenario: {
                    "count": fb.annotation_count,
                    "top_corrections": dict(
                        sorted(
                            fb.corrected_action_counts.items(),
                            key=lambda x: -x[1],
                        )[:3]
                    ),
                }
                for scenario, fb in self._feedback_adapter.get_aggregated().items()
            },
        }

    # ── Internal gap computations ───────────────────────────────────────

    @staticmethod
    def _compute_training_gap(samples: List[RealitySample]) -> float:
        """Training gap: loss instability / lack of convergence."""
        if len(samples) < 10:
            return 0.0

        # Sort by episode_id ascending to get chronological order
        sorted_samples = sorted(samples, key=lambda s: s.episode_id)

        losses = [s.loss for s in sorted_samples if s.loss is not None]
        if len(losses) < 10:
            return 0.0

        # Compare first half vs second half mean loss
        mid = len(losses) // 2
        first_half = sum(losses[:mid]) / mid
        second_half = sum(losses[mid:]) / (len(losses) - mid)

        if first_half <= 0:
            return 0.0

        # Gap = how much worse the second half is relative to first
        # (negative = improvement, clamp to 0)
        ratio = (second_half - first_half) / first_half
        return max(0.0, ratio)

    @staticmethod
    def _compute_feedback_gap(samples: List[RealitySample]) -> float:
        """Feedback gap: ratio of corrections to total feedback."""
        if not samples:
            return 0.0
        corrections = sum(
            1 for s in samples if s.corrected_action is not None
        )
        return corrections / len(samples)

    @staticmethod
    def _compute_shadow_gap(metrics: Dict) -> float:
        """Shadow gap: winrate non-monotonicity."""
        trend = metrics.get("winrate_trend", [])
        if len(trend) < 2:
            return 0.0

        # Count regressions (drops in winrate)
        regressions = sum(
            1 for i in range(1, len(trend))
            if trend[i] < trend[i - 1]
        )
        return regressions / (len(trend) - 1)

    @staticmethod
    def _classify_severity(gap: float) -> Severity:
        if gap < 0.05:
            return Severity.NONE
        elif gap < 0.15:
            return Severity.LOW
        elif gap < 0.30:
            return Severity.MEDIUM
        elif gap < 0.50:
            return Severity.HIGH
        return Severity.CRITICAL

    @staticmethod
    def _format_detail(
        sim_gap: float, train_gap: float,
        fb_gap: float, shadow_gap: float,
    ) -> str:
        parts = []
        if sim_gap > 0.10:
            parts.append(f"simulation winrate below expectations ({sim_gap:.1%})")
        if train_gap > 0.10:
            parts.append(f"training loss not converging ({train_gap:.1%})")
        if fb_gap > 0.20:
            parts.append(f"high user correction rate ({fb_gap:.1%})")
        if shadow_gap > 0.20:
            parts.append(f"shadow loop winrate regressions ({shadow_gap:.1%})")
        return "; ".join(parts) if parts else "all channels aligned"
