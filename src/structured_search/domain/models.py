"""Domain models for structured search: universal, task-agnostic.

This module defines the core abstractions: constraints, evidence, results.
Scoring configuration is separated to infra/scoring_config.py.
Task-specific models go in tasks/<name>/models.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import AnyUrl, BaseModel, ConfigDict, Field, model_validator

# ============================================================================
# Constraint Rules (Universal)
# ============================================================================


class ConstraintRule(BaseModel):
    """A single constraint rule: must/prefer/avoid item.

    Universal across all tasks. Task-specific fields (e.g., elasticity_pct)
    should extend this class or be handled in task-specific config.
    """

    field: str = Field(..., description="Dot-separated field path (e.g., 'geo.region')")
    op: Literal["=", "in", "contains_any", "contains_all", ">=", "<=", "<", ">", "weighted"] = (
        Field(
            ...,
            description="Operator: =, in, contains_any, contains_all, >=, <=, <, >, weighted",
        )
    )
    value: Any = Field(..., description="Target value(s) for the operator")
    weight: float = Field(1.0, description="Weight for prefer/avoid rules")
    weights: list[float] | None = Field(
        None, description="Weights for weighted operator (must match value length)"
    )
    neutral_if_na: bool = Field(False, description="Skip scoring if value is missing")
    severity: float | None = Field(None, description="Penalty severity for avoid rules")
    reason: str | None = Field(None, description="Human-readable reason for the constraint")
    time_decay_half_life_days: int | None = Field(
        None, description="Time decay parameter (soft constraint)"
    )

    @model_validator(mode="after")
    def _validate_operator_payload(self) -> ConstraintRule:
        list_ops = {"in", "contains_any", "contains_all", "weighted"}
        compare_ops = {">=", "<=", "<", ">"}

        if self.op in list_ops:
            if not isinstance(self.value, list):
                raise ValueError(f"op '{self.op}' requires 'value' to be a list")
            if len(self.value) == 0:
                raise ValueError(f"op '{self.op}' requires a non-empty 'value' list")

        if self.op in compare_ops and (
            not isinstance(self.value, (int, float)) or isinstance(self.value, bool)
        ):
            raise ValueError(f"op '{self.op}' requires numeric 'value'")

        if self.op == "weighted":
            if self.weights is None:
                raise ValueError("op 'weighted' requires 'weights'")
            if len(self.weights) != len(self.value):
                raise ValueError("op 'weighted' requires len(weights) == len(value)")
        elif self.weights is not None:
            raise ValueError("'weights' is only valid when op='weighted'")

        return self


class Sources(BaseModel):
    """Source configuration."""

    primary: list[str] = Field(default_factory=list)
    secondary: list[str] = Field(default_factory=list)
    fallback: list[str] = Field(default_factory=list)


class RelaxationPolicy(BaseModel):
    """Relaxation policy for constraint expansion."""

    order: list[str] = Field(default_factory=list, description="Order of relaxation steps")
    steps: dict[str, Any] = Field(default_factory=dict, description="Per-step relaxation config")
    emit_constraints_diff: bool = Field(False)


class BaseConstraints(BaseModel):
    """Base constraint configuration: must/prefer/avoid rules.

    Universal across all tasks. No scoring-specific fields.
    """

    domain: str = Field(..., description="Domain name (e.g., 'job_search')")
    sources: Sources = Field(default_factory=Sources)
    must: list[ConstraintRule] = Field(default_factory=list, description="Hard must-have rules")
    prefer: list[ConstraintRule] = Field(default_factory=list, description="Soft preference rules")
    avoid: list[ConstraintRule] = Field(default_factory=list, description="Soft avoid rules")
    limits: dict[str, Any] = Field(default_factory=dict)
    relaxation: RelaxationPolicy = Field(default_factory=RelaxationPolicy)


# ============================================================================
# User Profile (Universal Base)
# ============================================================================


class BaseUserProfile(BaseModel):
    """Base user profile configuration.

    Universal across all tasks. Task-specific extensions in models/{task}.py.
    """

    timezone: str = Field(..., description="User timezone (e.g., 'Europe/Madrid')")
    mobility: str = Field(..., description="Geographic mobility (e.g., 'regional/EU/US')")
    risk_tolerance: str = Field("medium", description="Risk tolerance level")
    currency_default: str = Field("EUR", description="Default currency")
    language_preference: list[str] = Field(default_factory=list)


# ============================================================================
# Evidence (Universal)
# ============================================================================


class EvidenceLocator(BaseModel):
    """Locator for evidence in source document."""

    type: str = Field(
        ...,
        description="Locator type: css_selector, xpath, pdf_page, line_range, text_fragment, url_fragment",
    )
    value: str = Field(..., description="The locator value")


class EvidenceAnchor(BaseModel):
    """Anchor for a piece of evidence.

    Links a record field to source material with precise location.
    """

    id: str = Field(..., description="Unique ID for this evidence")
    field: str = Field(..., description="Field this evidence supports")
    quote: str = Field(..., description="Direct quote from source")
    url: AnyUrl = Field(..., description="URL of evidence source")
    retrieved_at: datetime = Field(..., description="When evidence was retrieved")
    locator: EvidenceLocator = Field(..., description="Location in source")
    source_kind: str = Field("other", description="html, pdf, api, or other")
    is_external_instruction: bool = Field(False)


class FactRecord(BaseModel):
    """An observed fact backed by evidence."""

    field: str = Field(..., description="Field this fact populates")
    value: Any = Field(..., description="The fact value")
    evidence_ids: list[str] = Field(..., description="IDs of supporting evidence")


class InferenceRecord(BaseModel):
    """A derived inference with reasoning and confidence."""

    field: str = Field(..., description="Field this inference populates")
    value: Any = Field(..., description="The inferred value")
    reason: str = Field(..., description="Reasoning behind the inference")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence [0,1]")
    evidence_ids: list[str] = Field(..., description="IDs of supporting evidence")


# ============================================================================
# Base Result (Universal, Task-Agnostic)
# ============================================================================


class BaseResult(BaseModel):
    """Base result record: works for any task.

    Includes:
    - Core data (id, source, extracted_at)
    - Evidence model (evidence anchors, facts, inferences)
    - Quality indicators (anomalies, incomplete)
    - Metadata (extra dict for task-specific fields)

    Task-specific results inherit from this and add domain fields.
    Scoring results inherit separately and add gate_passed, score, etc.
    """

    model_config = ConfigDict(extra="allow")  # Allow task-specific fields

    # Identification
    id: str = Field(..., description="Unique record ID")
    source: str = Field(..., description="Source system or URL")

    # Extraction metadata
    extracted_at: datetime = Field(
        default_factory=datetime.now, description="When was this record extracted"
    )

    # Evidence & Quality
    evidence: list[EvidenceAnchor] = Field(
        default_factory=list, description="Evidence anchors supporting this record"
    )
    facts: list[FactRecord] = Field(
        default_factory=list, description="Observed facts with evidence"
    )
    inferences: list[InferenceRecord] = Field(
        default_factory=list, description="Derived inferences with reasoning"
    )

    # Quality indicators
    anomalies: list[str] = Field(default_factory=list, description="Detected anomalies")
    incomplete: bool = Field(False, description="Is this record incomplete?")
    notes: str | None = Field(None, description="Human-readable notes")
