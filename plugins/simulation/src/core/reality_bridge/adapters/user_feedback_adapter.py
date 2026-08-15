"""User feedback adapter: human annotations as soft constraints.

Parses feedback from:
  - Structured feedback files (JSON/YAML with scenario annotations)
  - Conversation logs (natural language extracted via keyword matching)
  - Inline markers: "# feedback: ..." in training configs

The adapter converts human intent into RealitySamples that the
meta-theory layer can use to detect perception-reality gaps.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models import Channel, FeedbackSample, RealitySample


class UserFeedbackAdapter:
    """Collect, parse, and aggregate human feedback."""

    # Keywords that indicate user correction or annotation intent
    _CORRECTION_KEYWORDS = [
        r"(?:should|shouldn't|should not)\s+(?:have\s+)?(?:push|turn|retreat|attack|defend|stop|go|move)",
        r"(?:wrong|incorrect|bad)\s+(?:action|move|decision|behavior)",
        r"correct(?:ed)?\s+(?:action|to)\s*[:=]?\s*(\d+)",
        r"prefer\s+(?:action)\s*[:=]?\s*(\d+)",
        r"#\s*feedback\s*:\s*(.+)",
    ]

    _SCENARIO_KEYWORDS = [
        r"edge[_ ]?case",
        r"corner[_ ]?case",
        r"scenario\s*[:=]\s*(\w+)",
        r"intentional\s+(push|ram|hit|shove)",
    ]

    def __init__(self, label: str = "human_feedback"):
        self._label = label
        self._aggregated: Dict[str, FeedbackSample] = {}

    # ── Public API ──────────────────────────────────────────────────────

    def parse_file(self, path: Path) -> List[RealitySample]:
        """Parse a structured feedback file.

        Supported formats:
          - JSON: [{"scenario": "...", "annotation": "...", ...}, ...]
          - YAML: list of feedback entries
          - Plain text: line-by-line keyword extraction
        """
        suffix = path.suffix.lower()
        if suffix == ".json":
            return self._parse_json(path)
        elif suffix in (".yaml", ".yml"):
            return self._parse_yaml(path)
        else:
            return self._parse_text(path)

    def parse_text(self, text: str, source: str = "inline") -> List[RealitySample]:
        """Parse feedback from raw text (e.g., conversation excerpt)."""
        samples: List[RealitySample] = []

        for pattern in self._CORRECTION_KEYWORDS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                annotation = match.group(0).strip()
                scenario = self._extract_scenario(text, match.start())

                # Try to extract corrected action number
                corrected_action = None
                if match.lastindex and match.lastindex >= 1:
                    try:
                        corrected_action = int(match.group(1))
                    except (ValueError, IndexError):
                        pass

                samples.append(RealitySample(
                    channel=Channel.USER_FEEDBACK,
                    timestamp=time.time(),
                    annotation=annotation,
                    corrected_action=corrected_action,
                    confidence=0.8,  # keyword-match confidence
                    tags=[self._label, source, scenario or "unlabeled"],
                ))

                self._update_aggregate(scenario or "unlabeled", annotation, corrected_action)

        return samples

    def parse_conversation_log(self, path: Path) -> List[RealitySample]:
        """Parse a conversation transcript for implicit feedback."""
        if not path.exists():
            return []
        text = path.read_text(encoding="utf-8", errors="replace")
        return self.parse_text(text, source=path.name)

    def add_explicit_feedback(
        self,
        scenario: str,
        annotation: str,
        corrected_action: Optional[int] = None,
        confidence: float = 1.0,
        obs: Optional[List[float]] = None,
        action_taken: Optional[int] = None,
    ) -> RealitySample:
        """Programmatically add a feedback entry (used by inline markers)."""
        sample = RealitySample(
            channel=Channel.USER_FEEDBACK,
            timestamp=time.time(),
            annotation=annotation,
            corrected_action=corrected_action,
            confidence=confidence,
            obs=obs,
            action=action_taken,
            tags=[self._label, scenario, "explicit"],
        )
        self._update_aggregate(scenario, annotation, corrected_action)
        return sample

    def get_aggregated(self) -> Dict[str, FeedbackSample]:
        """Return scenario-level feedback summaries."""
        return dict(self._aggregated)

    def get_scenario_feedback(self, scenario: str) -> Optional[FeedbackSample]:
        """Get aggregated feedback for a specific scenario."""
        return self._aggregated.get(scenario)

    # ── Internal ────────────────────────────────────────────────────────

    def _parse_json(self, path: Path) -> List[RealitySample]:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            data = [data]
        samples: List[RealitySample] = []
        for entry in data:
            samples.append(self.add_explicit_feedback(
                scenario=entry.get("scenario", "unlabeled"),
                annotation=entry.get("annotation", ""),
                corrected_action=entry.get("corrected_action"),
                confidence=entry.get("confidence", 1.0),
            ))
        return samples

    def _parse_yaml(self, path: Path) -> List[RealitySample]:
        # Minimal YAML parser — handles simple list-of-dicts
        text = path.read_text(encoding="utf-8", errors="replace")
        # Fallback: interpret as plain text with JSON-like entries
        samples: List[RealitySample] = []
        # Try to extract YAML list items
        current: Dict[str, Any] = {}
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("- "):
                if current:
                    samples.append(self._entry_to_sample(current))
                current = {}
                line = line[2:]
            if ":" in line and not line.startswith("#"):
                key, _, val = line.partition(":")
                current[key.strip()] = val.strip().strip('"').strip("'")
        if current:
            samples.append(self._entry_to_sample(current))
        return samples

    def _parse_text(self, path: Path) -> List[RealitySample]:
        text = path.read_text(encoding="utf-8", errors="replace")
        return self.parse_text(text, source=path.name)

    def _entry_to_sample(self, entry: Dict[str, Any]) -> RealitySample:
        return self.add_explicit_feedback(
            scenario=entry.get("scenario", "unlabeled"),
            annotation=entry.get("annotation", ""),
            corrected_action=(
                int(entry["corrected_action"])
                if "corrected_action" in entry and entry["corrected_action"]
                else None
            ),
            confidence=float(entry.get("confidence", 1.0)),
        )

    def _extract_scenario(self, text: str, position: int) -> Optional[str]:
        """Try to find a nearby scenario label."""
        window = text[max(0, position - 200):position]
        for pattern in self._SCENARIO_KEYWORDS:
            match = re.search(pattern, window, re.IGNORECASE)
            if match:
                if match.lastindex and match.lastindex >= 1:
                    return match.group(1)
                return match.group(0)
        return None

    def _update_aggregate(
        self,
        scenario: str,
        annotation: str,
        corrected_action: Optional[int],
    ) -> None:
        if scenario not in self._aggregated:
            self._aggregated[scenario] = FeedbackSample(scenario_label=scenario)

        fb = self._aggregated[scenario]
        fb.annotation_count += 1
        fb.description = annotation[:200] if annotation else fb.description

        if corrected_action is not None:
            fb.corrected_action_counts[corrected_action] = (
                fb.corrected_action_counts.get(corrected_action, 0) + 1
            )

        # Rolling average confidence
        n = fb.annotation_count
        fb.avg_confidence = (fb.avg_confidence * (n - 1) + 0.8) / n if n > 1 else 0.8
