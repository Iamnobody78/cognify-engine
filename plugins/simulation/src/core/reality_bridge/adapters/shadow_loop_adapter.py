"""Shadow loop adapter: rule evolution + gate decision history.

The shadow loop records:
  1. ABDL rule evolution — which rules were added/removed/modified
  2. Gate decisions — which of the 3/5 gates passed/rejected each action
  3. Version snapshots — rule sets at each version checkpoint

This adapter reads those artifacts and emits RealitySamples that
allow the meta-theory layer to analyze whether rule evolution
improves alignment with reality.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from ..models import Channel, RealitySample


class ShadowLoopAdapter:
    """Parse shadow loop artifacts into RealitySamples."""

    def __init__(self, label: str = "shadow_loop"):
        self._label = label

    # ── Public API ──────────────────────────────────────────────────────

    def parse_rule_evolution(self, path: Path) -> List[RealitySample]:
        """Parse a rule evolution log file.

        Expected format (CSV):
          version, rule_id, action, description
        or (JSON):
          [{"version": "v9.3", "rule_id": "R001", "action": "add", "desc": "..."}]
        """
        if not path.exists():
            return []

        suffix = path.suffix.lower()
        if suffix == ".json":
            return self._parse_rule_json(path)
        return self._parse_rule_csv(path)

    def parse_gate_history(self, path: Path) -> List[RealitySample]:
        """Parse gate decision history.

        Expected format (JSON):
          [{"episode": 1, "step": 5, "version": "v9.3",
            "gates": {"symbolic": true, "fuzzy": false, "nn": true}, "action": 3}]
        """
        if not path.exists():
            return []

        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            data = json.load(fh)

        if isinstance(data, dict):
            data = [data]

        samples: List[RealitySample] = []
        for entry in data:
            samples.append(RealitySample(
                channel=Channel.SHADOW_LOOP,
                timestamp=time.time(),
                episode_id=entry.get("episode", 0),
                step=entry.get("step", 0),
                action=entry.get("action"),
                rule_version=entry.get("version", "unknown"),
                gate_decisions=entry.get("gates", {}),
                reward=entry.get("reward", 0.0),
                win=entry.get("win", False),
                tags=[self._label, "gate_history"],
            ))
        return samples

    def parse_version_snapshot(self, path: Path) -> List[RealitySample]:
        """Parse a version snapshot — the full rule set at a given version.

        Expected format (JSON):
          {"version": "v9.3", "rules": [...], "stats": {...}}
        """
        if not path.exists():
            return []

        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            data = json.load(fh)

        version = data.get("version", "unknown")
        stats = data.get("stats", {})
        rules = data.get("rules", [])

        # Emit one sample per ruleset
        return [RealitySample(
            channel=Channel.SHADOW_LOOP,
            timestamp=time.time(),
            rule_version=version,
            reward=stats.get("winrate", 0.0),
            win=stats.get("winrate", 0.0) > 0.5,
            episode_length=stats.get("total_episodes", 0),
            tags=[self._label, "version_snapshot", version],
            extra={
                "rule_count": len(rules),
                "stats": stats,
            },
        )]

    def iter_versions(self, directory: Path) -> Iterator[RealitySample]:
        """Iterate all version snapshots in a directory."""
        for fp in sorted(directory.glob("*.json")):
            samples = self.parse_version_snapshot(fp)
            yield from samples

    def compute_evolution_metrics(
        self, samples: List[RealitySample]
    ) -> Dict[str, Any]:
        """Compute high-level metrics from shadow loop samples.

        Returns:
            {
                "versions_observed": ["v9.1", "v9.2", "v9.3"],
                "rule_churn": 12,        # rules added + removed
                "gate_pass_rate": {       # per-gate pass rate
                    "symbolic": 0.85,
                    "fuzzy": 0.72,
                    "nn": 0.91,
                },
                "winrate_trend": [0.3, 0.4, 0.47],  # per-version winrate
            }
        """
        versions: Dict[str, float] = {}   # version -> winrate
        gate_passes: Dict[str, int] = {}   # gate -> pass count
        gate_totals: Dict[str, int] = {}   # gate -> total count
        total_rules_changed = 0

        for s in samples:
            v = s.rule_version or "unknown"
            if v not in versions:
                versions[v] = s.reward if s.reward else 0.0

            if s.gate_decisions:
                for gate, passed in s.gate_decisions.items():
                    gate_totals[gate] = gate_totals.get(gate, 0) + 1
                    if passed:
                        gate_passes[gate] = gate_passes.get(gate, 0) + 1

            total_rules_changed += s.extra.get("rule_count", 0)

        gate_pass_rate = {
            g: gate_passes[g] / max(gate_totals[g], 1)
            for g in gate_totals
        }

        return {
            "versions_observed": sorted(versions.keys()),
            "rule_churn": total_rules_changed,
            "gate_pass_rate": gate_pass_rate,
            "winrate_trend": [
                versions[v] for v in sorted(versions.keys())
            ],
        }

    # ── Internal ────────────────────────────────────────────────────────

    def _parse_rule_json(self, path: Path) -> List[RealitySample]:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            data = [data]

        samples: List[RealitySample] = []
        for entry in data:
            action = 1 if entry.get("action") == "add" else -1
            samples.append(RealitySample(
                channel=Channel.SHADOW_LOOP,
                timestamp=time.time(),
                rule_version=entry.get("version", "unknown"),
                reward=float(action),   # +1 for add, -1 for remove
                tags=[self._label, "rule_evolution", entry.get("action", "unknown")],
                extra={
                    "rule_id": entry.get("rule_id", ""),
                    "action": entry.get("action", ""),
                    "desc": entry.get("desc", ""),
                },
            ))
        return samples

    def _parse_rule_csv(self, path: Path) -> List[RealitySample]:
        import csv
        samples: List[RealitySample] = []
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                action_str = row.get("action", "")
                reward = 1.0 if action_str == "add" else -1.0
                samples.append(RealitySample(
                    channel=Channel.SHADOW_LOOP,
                    timestamp=time.time(),
                    rule_version=row.get("version", "unknown"),
                    reward=reward,
                    tags=[self._label, "rule_evolution", action_str],
                    extra={
                        "rule_id": row.get("rule_id", ""),
                        "action": action_str,
                        "desc": row.get("desc", ""),
                    },
                ))
        return samples
