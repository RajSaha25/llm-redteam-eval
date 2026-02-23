"""
Core data models for llm-redteam-eval.

Design principles:
- Cases are the source of truth. They encode the hypothesis, setup, and scoring criteria.
- RunResults capture model outputs without annotation. Annotation is layered on top.
- Models serialize cleanly to JSON for storage and diffing.

Compatibility: supports Pydantic v1 and v2.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

import pydantic
from pydantic import BaseModel, Field

PYDANTIC_V2 = int(pydantic.VERSION.split(".")[0]) >= 2


def _parse(model_cls, data: dict):
    """Parse a dict into a Pydantic model, v1/v2 compatible."""
    if PYDANTIC_V2:
        return model_cls.model_validate(data)
    return model_cls.parse_obj(data)


def _dump(instance, mode: str = "json") -> dict:
    """Serialize a Pydantic model to a dict, v1/v2 compatible."""
    if PYDANTIC_V2:
        return instance.model_dump(mode=mode)
    # v1: .dict() returns Python objects; datetimes won't serialize without default=str
    return instance.dict()


# ---------------------------------------------------------------------------
# Case schema — what a test case looks like on disk
# ---------------------------------------------------------------------------


class FailureSignal(BaseModel):
    """A human-readable description of what a failure looks like for this case."""

    id: str
    description: str
    detection_hint: str = ""
    # Optional regex pattern for lightweight automated pre-screening.
    # Not a substitute for human judgment — just a triage aid.
    automated_pattern: str | None = None


class ScoringCriterion(BaseModel):
    """A single scoreable dimension of the case."""

    id: str
    description: str
    weight: float = 1.0


class Scoring(BaseModel):
    type: Literal["human", "automated", "hybrid"] = "human"
    criteria: list[ScoringCriterion] = Field(default_factory=list)


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ToolDefinition(BaseModel):
    """Minimal tool spec matching the Anthropic tool_use format."""

    name: str
    description: str
    input_schema: dict[str, Any]


class Setup(BaseModel):
    system_prompt: str | None = None
    tools: list[ToolDefinition] | None = None
    # For indirect-injection and tool-misuse cases: maps tool_name -> simulated output.
    # The runner intercepts tool_use stop events and returns these instead of
    # calling real tools, keeping cases self-contained.
    simulated_tool_results: dict[str, str] | None = None


class Case(BaseModel):
    id: str
    title: str
    category: str
    subcategory: str
    severity: Literal["low", "medium", "high", "critical"]
    description: str
    hypothesis: str
    setup: Setup
    turns: list[Turn]
    expected_behavior: str
    failure_signals: list[FailureSignal]
    scoring: Scoring
    tags: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Result schema — what gets written to disk after a run
# ---------------------------------------------------------------------------


class TurnResult(BaseModel):
    role: str
    content: str


class CriterionVerdict(BaseModel):
    criterion_id: str
    failed: bool
    note: str = ""


class Annotation(BaseModel):
    verdict: Literal["pass", "fail", "unclear"]
    notes: str = ""
    criterion_verdicts: list[CriterionVerdict] = Field(default_factory=list)
    annotated_by: str = "human"
    annotated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RunResult(BaseModel):
    case_id: str
    # Denormalized from the case for reporting convenience — avoids needing
    # to reload all case files just to produce a summary.
    category: str
    subcategory: str
    severity: str
    run_id: str
    model: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Full conversation as sent to the model (including any scripted turns).
    conversation: list[TurnResult]
    # The model's final response text.
    model_response: str
    annotation: Annotation | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
