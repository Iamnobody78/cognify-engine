"""
Module E: Observability + Guardrails — real-time tracing and input/output safety.
"""

import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ═══ TRACER ══════════════════════════════════════════════════════════════════


@dataclass
class Span:
    """A single trace span."""
    span_id: str
    name: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    success: bool = False
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    llm_calls: List[Dict] = field(default_factory=list)

    def close(self, success: bool = True):
        self.end_time = time.time()
        self.success = success

    @property
    def duration_ms(self) -> float:
        if self.end_time is None:
            return 0
        return (self.end_time - self.start_time) * 1000


@dataclass
class Tracer:
    """Observability tracer for Agent execution tracing."""

    trace_id: str
    spans: List[Span] = field(default_factory=list)
    _active_spans: Dict[str, Span] = field(default_factory=dict)

    def start_span(self, name: str, confidence: float = 1.0) -> str:
        """Start a new span, return span_id."""
        sid = f"span_{uuid.uuid4().hex[:8]}"
        span = Span(span_id=sid, name=name, confidence=confidence)
        self.spans.append(span)
        self._active_spans[sid] = span
        return sid

    def end_span(self, span_id: str, success: bool = True):
        """Close a span."""
        if span_id in self._active_spans:
            self._active_spans[span_id].close(success)
            del self._active_spans[span_id]

    def log_llm_call(self, model: str, tokens: int, confidence: float, cost_est: float = 0.0):
        """Log an LLM call on the most recent open span."""
        for span in reversed(self.spans):
            if not span.end_time:
                span.llm_calls.append({
                    "model": model,
                    "tokens": tokens,
                    "confidence": confidence,
                    "cost_est": cost_est,
                    "timestamp": time.time(),
                })
                break

    def total_tokens(self) -> int:
        return sum(sum(c["tokens"] for c in s.llm_calls) for s in self.spans)

    def total_cost_est(self) -> float:
        return sum(sum(c["cost_est"] for c in s.llm_calls) for s in self.spans)

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "spans": [
                {
                    "span_id": s.span_id,
                    "name": s.name,
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "duration_ms": s.duration_ms,
                    "success": s.success,
                    "confidence": s.confidence,
                    "llm_calls": s.llm_calls,
                    "metadata": s.metadata,
                }
                for s in self.spans
            ],
        }

    def save(self, base_dir: Optional[str] = None):
        """Persist trace to JSON file."""
        if base_dir is None:
            base_dir = os.path.join(os.path.dirname(__file__), "..", "..", ".aionui", "traces")
        os.makedirs(base_dir, exist_ok=True)
        path = os.path.join(base_dir, f"{self.trace_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)


# ── Global tracer factory ───────────────────────────────────────────────────

class TracerFactory:
    """Creates named tracers."""

    def __init__(self):
        self._tracers: Dict[str, Tracer] = {}

    def create(self, session_name: str = "") -> Tracer:
        tid = f"trace_{session_name or uuid.uuid4().hex[:12]}"
        t = Tracer(trace_id=tid)
        self._tracers[tid] = t
        return t

    def __call__(self, session_name: str = "") -> Tracer:
        return self.create(session_name)


tracer_factory = TracerFactory()


# ═══ GUARDRAILS ═════════════════════════════════════════════════════════════


@dataclass
class GuardrailResult:
    """Result of guardrail sanitization."""
    sanitized: str
    safe: bool
    issues: List[str] = field(default_factory=list)
    redacted: List[str] = field(default_factory=list)


@dataclass
class Guardrails:
    """Input/output safety filters."""

    # ── PII patterns ──
    PII_PATTERNS: Dict[str, str] = field(default_factory=lambda: {
        "email": r'[\w\.-]+@[\w\.-]+\.\w+',
        "phone": r'\+?[\d\s\(\)-]{7,15}',
        "ip_v4": r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b',
    })

    # ── Dangerous patterns ──
    DANGEROUS_PATTERNS: List[Tuple[str, str]] = field(default_factory=lambda: [
        ("rm_rf", r'\brm\s+-rf\b'),
        ("eval_exec", r'\b(eval|exec|__import__)\s*\('),
        ("os_system", r'\bos\.system\s*\('),
        ("subprocess_shell", r'\bsubprocess\.(run|Popen|call)\b.*shell\s*=\s*True'),
    ])

    _output_dangerous: List[Tuple[str, str]] = field(default_factory=lambda: [
        ("eval_exec", r'\b(eval|exec)\s*\('),
    ])

    def sanitize_input(self, text: str) -> GuardrailResult:
        """Check and sanitize user input."""
        issues: List[str] = []
        redacted: List[str] = []
        sanitized = text

        # Check dangerous patterns
        for name, pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, sanitized, re.IGNORECASE):
                issues.append(f"dangerous:{name}")
                sanitized = re.sub(pattern, "[BLOCKED:" + name + "]", sanitized, flags=re.IGNORECASE)

        # Redact PII
        for name, pattern in self.PII_PATTERNS.items():
            if re.search(pattern, sanitized):
                redacted.append(name)
                sanitized = re.sub(pattern, f"[REDACTED:{name}]", sanitized)

        return GuardrailResult(
            sanitized=sanitized,
            safe=len(issues) == 0,
            issues=issues,
            redacted=redacted,
        )

    def sanitize_output(self, text: str) -> GuardrailResult:
        """Check and sanitize Agent output."""
        issues: List[str] = []
        sanitized = text

        for name, pattern in self._output_dangerous:
            if re.search(pattern, sanitized, re.IGNORECASE):
                issues.append(f"dangerous:{name}")
                sanitized = re.sub(pattern, "[FLAGGED:" + name + "]", sanitized, flags=re.IGNORECASE)

        return GuardrailResult(
            sanitized=sanitized,
            safe=len(issues) == 0,
            issues=issues,
        )


# ── Global singleton ────────────────────────────────────────────────────────

tracer = tracer_factory
guardrails = Guardrails()
