"""RealityBridge data models.

Unified schemas for all 4 input channels and the bridge output.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Channel(str, Enum):
    """Data source channel identifier."""
    SIMULATION = "simulation"       # lightweight env / Gazebo
    TRAINING_LOG = "training_log"   # DQN/SAC/TD3 training metrics
    USER_FEEDBACK = "user_feedback"  # human annotations
    SHADOW_LOOP = "shadow_loop"     # rule evolution + gate history


class Severity(str, Enum):
    """Gap severity in the perception-reality alignment."""
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RealitySample:
    """A single observation from any channel, normalized for meta-analysis.

    This is the canonical data unit that flows from the real world
    (or simulation) into the meta-governance layer.
    """

    sample_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    channel: Channel = Channel.SIMULATION
    timestamp: float = field(default_factory=time.time)

    # ── Episode context ──
    episode_id: int = 0
    step: int = 0

    # ── Observation (7-dim BottleSumo vector) ──
    # [edge_f, edge_b, edge_l, edge_r, opp_dist, opp_angle, speed]
    obs: Optional[List[float]] = None

    # ── Action taken ──
    action: Optional[int] = None  # 0-20 discrete action

    # ── Outcome metrics ──
    reward: float = 0.0
    win: bool = False
    episode_length: int = 0

    # ── Training-specific (channel=training_log) ──
    loss: Optional[float] = None
    q_value: Optional[float] = None
    epsilon: Optional[float] = None
    lr: Optional[float] = None

    # ── User feedback (channel=user_feedback) ──
    annotation: Optional[str] = None        # e.g. "intentional push"
    corrected_action: Optional[int] = None   # human-corrected action
    confidence: float = 1.0                  # annotator confidence [0, 1]

    # ── Shadow loop (channel=shadow_loop) ──
    rule_version: Optional[str] = None       # e.g. "v9.3"
    gate_decisions: Optional[Dict[str, bool]] = None  # {symbolic: True, fuzzy: False, ...}

    # ── Free-form metadata ──
    tags: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a flat dict for JSON/SQLite storage."""
        return {
            "sample_id": self.sample_id,
            "channel": self.channel.value,
            "timestamp": self.timestamp,
            "episode_id": self.episode_id,
            "step": self.step,
            "obs": self.obs,
            "action": self.action,
            "reward": self.reward,
            "win": int(self.win),
            "episode_length": self.episode_length,
            "loss": self.loss,
            "q_value": self.q_value,
            "epsilon": self.epsilon,
            "lr": self.lr,
            "annotation": self.annotation,
            "corrected_action": self.corrected_action,
            "confidence": self.confidence,
            "rule_version": self.rule_version,
            "gate_decisions": self.gate_decisions,
            "tags": self.tags,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RealitySample":
        """Deserialize from a flat dict."""
        return cls(
            sample_id=d.get("sample_id", uuid.uuid4().hex[:12]),
            channel=Channel(d.get("channel", "simulation")),
            timestamp=d.get("timestamp", time.time()),
            episode_id=d.get("episode_id", 0),
            step=d.get("step", 0),
            obs=d.get("obs"),
            action=d.get("action"),
            reward=d.get("reward", 0.0),
            win=bool(d.get("win", False)),
            episode_length=d.get("episode_length", 0),
            loss=d.get("loss"),
            q_value=d.get("q_value"),
            epsilon=d.get("epsilon"),
            lr=d.get("lr"),
            annotation=d.get("annotation"),
            corrected_action=d.get("corrected_action"),
            confidence=d.get("confidence", 1.0),
            rule_version=d.get("rule_version"),
            gate_decisions=d.get("gate_decisions"),
            tags=d.get("tags", []),
            extra=d.get("extra", {}),
        )


@dataclass
class FeedbackSample:
    """Aggregated user feedback for a specific scenario or behavior."""

    feedback_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    scenario_label: str = ""           # e.g. "edge_defense_v1"
    description: str = ""
    annotation_count: int = 0
    corrected_action_counts: Dict[int, int] = field(default_factory=dict)
    avg_confidence: float = 0.0
    tags: List[str] = field(default_factory=list)


@dataclass
class GapReport:
    """Perception-reality gap analysis.

    Answers: "Does the meta-theory's understanding of the world
    match what the sensors/training/logs actually show?"
    """

    report_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    generated_at: float = field(default_factory=time.time)

    # ── Gap metrics per channel ──
    simulation_gap: float = 0.0        # expected vs actual winrate
    training_gap: float = 0.0          # Q-value stability vs trajectory quality
    user_feedback_gap: float = 0.0     # agent decisions vs human corrections
    shadow_loop_gap: float = 0.0       # evolved rules vs actual executions

    # ── Aggregate ──
    overall_gap: float = 0.0           # weighted average
    severity: Severity = Severity.NONE
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "generated_at": self.generated_at,
            "simulation_gap": self.simulation_gap,
            "training_gap": self.training_gap,
            "user_feedback_gap": self.user_feedback_gap,
            "shadow_loop_gap": self.shadow_loop_gap,
            "overall_gap": self.overall_gap,
            "severity": self.severity.value,
            "detail": self.detail,
        }
