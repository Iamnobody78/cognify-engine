"""
Module A: Structured Output Engine — eliminates "format hallucination".
Enforces JSON Schema output for critical decisions via Pydantic models.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    from pydantic import BaseModel, Field, ValidationError
    _PydanticModel = BaseModel
except ImportError:
    _PydanticModel = object


# ── Schema Models ───────────────────────────────────────────────────────────

class TaskPlan(_PydanticModel if _PydanticModel is not object else object):
    """Structured task plan output schema."""

    task_id: str = Field(description="Unique task identifier")
    goal: str = Field(description="Task goal description")
    steps: List[str] = Field(description="Ordered execution steps")
    dependencies: Optional[List[str]] = Field(default=None, description="IDs of prerequisite tasks")


class DecisionOutput(_PydanticModel if _PydanticModel is not object else object):
    """Structured decision output schema."""

    decision: str = Field(description="Decision result")
    confidence: float = Field(ge=0, le=1, description="Confidence score")
    reasoning: str = Field(description="Rationale for the decision")
    alternatives: List[str] = Field(default_factory=list, description="Alternative options considered")


class CodeGenOutput(_PydanticModel if _PydanticModel is not object else object):
    """Structured code generation output schema."""

    language: str
    filename: str
    code: str
    description: str
    tests: Optional[str] = None
    dependencies: List[str] = Field(default_factory=list)


class AnalysisOutput(_PydanticModel if _PydanticModel is not object else object):
    """Structured analysis output schema."""

    summary: str
    findings: List[Dict[str, str]] = Field(default_factory=list)
    severity: str = "info"  # info, warning, error, critical
    recommendations: List[str] = Field(default_factory=list)


# ── Decoder ─────────────────────────────────────────────────────────────────


@dataclass
class StructuredOutputDecoder:
    """Decodes raw LLM output into typed Pydantic models with fallback."""

    model_cls: type
    strict: bool = True

    def decode(self, raw: str) -> Optional[Any]:
        """Attempt to parse raw LLM output. Returns model instance or None."""
        import json
        import re

        # Strategy 1: Direct JSON
        try:
            data = json.loads(raw.strip())
            return self.model_cls(**data)
        except (json.JSONDecodeError, Exception):
            pass

        # Strategy 2: Extract JSON block from markdown
        m = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', raw)
        if m:
            try:
                data = json.loads(m.group(1))
                return self.model_cls(**data)
            except (json.JSONDecodeError, Exception):
                pass

        # Strategy 3: Extract first { ... } block
        m2 = re.search(r'\{[\s\S]*\}', raw)
        if m2:
            try:
                data = json.loads(m2.group(0))
                return self.model_cls(**data)
            except (json.JSONDecodeError, Exception):
                pass

        if self.strict:
            return None  # Fail explicitly

        # Strategy 4: Loose — try partial fields
        try:
            return self.model_cls(**{"task_id": raw[:50], "goal": raw[:200], "steps": [raw[:500]]})
        except Exception:
            return None


# ── Schema Registry ─────────────────────────────────────────────────────────

SCHEMA_REGISTRY: Dict[str, type] = {
    "task_plan": TaskPlan,
    "decision": DecisionOutput,
    "code_gen": CodeGenOutput,
    "analysis": AnalysisOutput,
}


def get_schema(name: str) -> Optional[type]:
    """Look up a schema by name."""
    return SCHEMA_REGISTRY.get(name)


def list_schemas() -> List[str]:
    """List all registered schema names."""
    return list(SCHEMA_REGISTRY.keys())
