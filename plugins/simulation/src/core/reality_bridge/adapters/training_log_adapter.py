"""Training log adapter: parses DQN/TD3 training logs into RealitySamples.

Parses standard training CSV/log files with columns:
  episode, loss, reward, win, epsilon, q_value, lr, steps

Also handles JSON-line training outputs.
"""
from __future__ import annotations

import csv
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from ..models import Channel, RealitySample


class TrainingLogAdapter:
    """Parse training artifacts (CSV, JSONL, log) into RealitySample streams."""

    # Known CSV column name aliases
    _COLUMN_MAP = {
        "episode": "episode",
        "ep": "episode",
        "epoch": "episode",
        "loss": "loss",
        "avg_loss": "loss",
        "mean_loss": "loss",
        "reward": "reward",
        "avg_reward": "reward",
        "mean_reward": "reward",
        "win": "win",
        "won": "win",
        "winrate": "win",
        "epsilon": "epsilon",
        "eps": "epsilon",
        "q_value": "q_value",
        "q_val": "q_value",
        "avg_q": "q_value",
        "lr": "lr",
        "learning_rate": "lr",
        "steps": "steps",
        "episode_length": "steps",
        "duration": "steps",
    }

    def __init__(self, label: str = "dqn_training"):
        self._label = label
        self._episode_offset = 0

    # ── Public API ──────────────────────────────────────────────────────

    def parse_csv(self, path: Path) -> List[RealitySample]:
        """Parse a standard training CSV."""
        samples: List[RealitySample] = []
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                s = self._row_to_sample(row)
                if s is not None:
                    samples.append(s)
        return samples

    def parse_jsonl(self, path: Path) -> List[RealitySample]:
        """Parse a JSON-lines training log."""
        samples: List[RealitySample] = []
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                s = self._dict_to_sample(obj)
                if s is not None:
                    samples.append(s)
        return samples

    def parse_directory(self, dir_path: Path, pattern: str = "*.csv") -> List[RealitySample]:
        """Parse all matching files in a directory."""
        all_samples: List[RealitySample] = []
        for fp in sorted(dir_path.glob(pattern)):
            if fp.suffix == ".csv":
                all_samples.extend(self.parse_csv(fp))
            elif fp.suffix in (".jsonl", ".json"):
                all_samples.extend(self.parse_jsonl(fp))
        return all_samples

    def iter_samples(self, path: Path) -> Iterator[RealitySample]:
        """Stream samples from a file without loading all into memory."""
        suffix = path.suffix.lower()
        if suffix == ".csv":
            yield from self._iter_csv(path)
        elif suffix in (".jsonl", ".json"):
            yield from self._iter_jsonl(path)

    # ── Internal ────────────────────────────────────────────────────────

    def _normalize_columns(self, headers: List[str]) -> Dict[str, int]:
        """Map CSV headers to canonical names."""
        mapping: Dict[str, int] = {}
        for idx, h in enumerate(headers):
            h_lower = h.strip().lower().replace(" ", "_")
            canonical = self._COLUMN_MAP.get(h_lower, h_lower)
            mapping[canonical] = idx
        return mapping

    def _row_to_sample(self, row: Dict[str, str]) -> Optional[RealitySample]:
        """Convert a CSV row dict to a RealitySample."""
        return self._dict_to_sample(dict(row))

    def _dict_to_sample(self, d: Dict[str, Any]) -> Optional[RealitySample]:
        """Convert any dict to a RealitySample by mapping keys."""
        # Map keys using the column map
        mapped: Dict[str, Any] = {}
        for key, val in d.items():
            canonical = self._COLUMN_MAP.get(key.strip().lower(), key.strip().lower())
            mapped[canonical] = val

        episode_id = int(float(mapped.get("episode", 0)))
        try:
            reward = float(mapped.get("reward", 0.0))
        except (ValueError, TypeError):
            reward = 0.0

        try:
            win = float(mapped.get("win", 0.0)) > 0.5
        except (ValueError, TypeError):
            win = False

        try:
            loss = float(mapped.get("loss", 0.0))
        except (ValueError, TypeError):
            loss = None

        try:
            q_value = float(mapped.get("q_value", 0.0))
        except (ValueError, TypeError):
            q_value = None

        try:
            epsilon = float(mapped.get("epsilon", 0.0))
        except (ValueError, TypeError):
            epsilon = None

        try:
            lr = float(mapped.get("lr", 0.0))
        except (ValueError, TypeError):
            lr = None

        try:
            steps = int(float(mapped.get("steps", 0)))
        except (ValueError, TypeError):
            steps = 0

        return RealitySample(
            channel=Channel.TRAINING_LOG,
            episode_id=episode_id + self._episode_offset,
            step=steps,
            reward=reward,
            win=win,
            loss=loss,
            q_value=q_value,
            epsilon=epsilon,
            lr=lr,
            episode_length=steps,
            tags=[self._label],
        )

    def _iter_csv(self, path: Path) -> Iterator[RealitySample]:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                s = self._row_to_sample(row)
                if s is not None:
                    yield s

    def _iter_jsonl(self, path: Path) -> Iterator[RealitySample]:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                s = self._dict_to_sample(obj)
                if s is not None:
                    yield s
