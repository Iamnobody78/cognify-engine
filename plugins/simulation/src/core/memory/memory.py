"""
Module B: Working Memory + Knowledge Graph.
Multi-step task tracing, rollback, and entity-relationship querying.
In-memory by default; JSON-file persistence for cross-session continuity.
"""

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class TraceStep:
    """A single step in a task execution trace."""

    step_id: int
    action: str
    result: str
    timestamp: float = field(default_factory=time.time)
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionMemory:
    """Working memory for a single multi-step task session."""

    session_id: str
    goal: str
    steps: List[TraceStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    status: str = "active"  # active, completed, rolled_back, failed

    def add_step(self, action: str, result: str, **meta) -> TraceStep:
        step = TraceStep(step_id=len(self.steps) + 1, action=action, result=result, metadata=meta)
        self.steps.append(step)
        return step

    def rollback_to(self, step_id: int) -> List[TraceStep]:
        """Roll back to a specific step, removing all subsequent steps."""
        removed = self.steps[step_id:]
        self.steps = self.steps[:step_id]
        self.status = "rolled_back"
        return removed

    def summary(self) -> str:
        """One-line summary of the session."""
        done = sum(1 for s in self.steps if s.confidence >= 0.8)
        return f"[{self.session_id}] {self.goal} — {len(self.steps)} steps ({done} confident)"

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "goal": self.goal,
            "steps": [
                {
                    "step_id": s.step_id,
                    "action": s.action,
                    "result": s.result,
                    "timestamp": s.timestamp,
                    "confidence": s.confidence,
                    "metadata": s.metadata,
                }
                for s in self.steps
            ],
            "created_at": self.created_at,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionMemory":
        s = cls(session_id=data["session_id"], goal=data.get("goal", ""))
        s.status = data.get("status", "active")
        s.created_at = data.get("created_at", time.time())
        for sd in data.get("steps", []):
            s.steps.append(
                TraceStep(
                    step_id=sd["step_id"],
                    action=sd.get("action", ""),
                    result=sd.get("result", ""),
                    timestamp=sd.get("timestamp", time.time()),
                    confidence=sd.get("confidence", 1.0),
                    metadata=sd.get("metadata", {}),
                )
            )
        return s


# ── Working Memory Manager ──────────────────────────────────────────────────


class WorkingMemory:
    """Manages active task sessions."""

    def __init__(self, persist_path: Optional[str] = None):
        self._sessions: Dict[str, SessionMemory] = {}
        self._persist_path = persist_path
        if persist_path and os.path.exists(persist_path):
            self._load()

    def create_session(self, goal: str) -> SessionMemory:
        sid = f"session_{uuid.uuid4().hex[:12]}"
        session = SessionMemory(session_id=sid, goal=goal)
        self._sessions[sid] = session
        return session

    def add_step(self, session_id: str, action: str, result: str, **meta):
        if session_id not in self._sessions:
            raise KeyError(f"Session {session_id} not found")
        return self._sessions[session_id].add_step(action, result, **meta)

    def rollback_to_step(self, session_id: str, step_id: int) -> List[TraceStep]:
        if session_id not in self._sessions:
            raise KeyError(f"Session {session_id} not found")
        return self._sessions[session_id].rollback_to(step_id)

    def get_session(self, session_id: str) -> Optional[SessionMemory]:
        return self._sessions.get(session_id)

    def list_sessions(self) -> List[str]:
        return list(self._sessions.keys())

    def close_session(self, session_id: str, status: str = "completed"):
        if session_id in self._sessions:
            self._sessions[session_id].status = status

    def _load(self):
        try:
            with open(self._persist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for d in data:
                s = SessionMemory.from_dict(d)
                self._sessions[s.session_id] = s
        except Exception:
            pass

    def save(self):
        if not self._persist_path:
            return
        os.makedirs(os.path.dirname(self._persist_path), exist_ok=True)
        with open(self._persist_path, "w", encoding="utf-8") as f:
            json.dump([s.to_dict() for s in self._sessions.values()], f, indent=2)


# ── Knowledge Graph ─────────────────────────────────────────────────────────


@dataclass
class KnowledgeGraph:
    """Simple in-memory entity-relationship graph."""

    entities: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    relations: List[Tuple[str, str, str]] = field(default_factory=list)
    # relations: (source, predicate, target)

    def add_entity(self, name: str, **attrs):
        if name not in self.entities:
            self.entities[name] = {}
        self.entities[name].update(attrs)

    def add_relation(self, source: str, predicate: str, target: str):
        self.relations.append((source, predicate, target))
        # Ensure both entities exist
        if source not in self.entities:
            self.entities[source] = {}
        if target not in self.entities:
            self.entities[target] = {}

    def get_entity(self, name: str) -> Optional[Dict[str, Any]]:
        return self.entities.get(name)

    def get_related_entities(self, name: str, max_depth: int = 2) -> Set[str]:
        """BFS to find all entities related to `name` up to max_depth."""
        visited: Set[str] = {name}
        frontier: Set[str] = {name}
        for _depth in range(max_depth):
            next_frontier: Set[str] = set()
            for s, _p, t in self.relations:
                if s in frontier and t not in visited:
                    next_frontier.add(t)
                    visited.add(t)
                if t in frontier and s not in visited:
                    next_frontier.add(s)
                    visited.add(s)
            frontier = next_frontier
        visited.discard(name)
        return visited

    def query_relations(self, source: Optional[str] = None, predicate: Optional[str] = None,
                        target: Optional[str] = None) -> List[Tuple[str, str, str]]:
        """Filter relations by any combination of source/predicate/target."""
        results = []
        for s, p, t in self.relations:
            if source and s != source:
                continue
            if predicate and p != predicate:
                continue
            if target and t != target:
                continue
            results.append((s, p, t))
        return results

    def to_dict(self) -> dict:
        return {
            "entities": self.entities,
            "relations": [list(r) for r in self.relations],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeGraph":
        kg = cls(entities=data.get("entities", {}))
        kg.relations = [tuple(r) for r in data.get("relations", [])]
        return kg


# ── Global singletons ───────────────────────────────────────────────────────

wm = WorkingMemory(persist_path=os.path.join(
    os.path.dirname(__file__), "..", "..", ".aionui", "memory", "working_sessions.json"
))
kg = KnowledgeGraph()

# Bootstrap with BottleSumo known entities
kg.add_relation("STM32F407", "runs_on", "PCB_Rev2")
kg.add_relation("PCB_Rev2", "contains", "VL53L0X")
kg.add_relation("VL53L0X", "uses", "I2C_Bus")
kg.add_relation("I2C_Bus", "connected_to", "F407_PB6_PB7")
kg.add_relation("STM32F103", "spi_communicates_with", "STM32F407")
