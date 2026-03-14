"""Shared Pydantic contracts used by API and application layers."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ValidationIssue(BaseModel):
    """A single validation problem with JSON-path context."""

    path: str
    code: str
    message: str
    severity: Literal["error", "warning"] = "error"


class TaskSummary(BaseModel):
    """Summary item from GET /v1/tasks."""

    task_id: str
    name: str
    capabilities: list[str] = Field(default_factory=list)


class ProfileBundle(BaseModel):
    """All editable config for one task/profile."""

    task_id: str = "job_search"
    profile_id: str
    constraints: dict[str, Any]
    task: dict[str, Any]
    task_config: dict[str, Any]
    user_profile: dict[str, Any] | None = None
    domain_schema: dict[str, Any] | None = None
    result_schema: dict[str, Any] | None = None


class ProfileSummary(BaseModel):
    """Summary item from GET /v1/tasks/{task_id}/profiles."""

    id: str
    name: str
    updated_at: str


class BundleSaveResponse(BaseModel):
    """Response from PUT bundle endpoint."""

    valid: bool
    issues: list[ValidationIssue]


class BundleWriteResponse(BaseModel):
    """HTTP response body for PUT bundle endpoint."""

    ok: bool
    version: str | None = None
    errors: list[ValidationIssue] = Field(default_factory=list)


class PromptResponse(BaseModel):
    """Prompt payload used by application services."""

    profile_id: str
    step: str
    prompt: str


class PromptGenerateRequest(BaseModel):
    """Request body for POST prompt generation."""

    profile_id: str
    step: str = "S3_execute"


class PromptGenerateResponse(BaseModel):
    """HTTP response body for POST prompt generation."""

    profile_id: str
    step: str
    prompt: str
    constraints_embedded: bool
    prompt_hash: str


class IngestError(BaseModel):
    """A single record-level error from JSONL ingestion."""

    line_no: int
    raw_preview: str
    kind: Literal["json_parse", "not_object", "schema_validation"]
    message: str


class IngestStats(BaseModel):
    total_lines: int
    parse_ok: int
    schema_ok: int
    parse_errors: int
    schema_errors: int


class IngestResult(BaseModel):
    """Result from JSONL validation."""

    valid: list[dict[str, Any]]
    invalid: list[IngestError]
    stats: IngestStats


class JsonlValidateRequest(BaseModel):
    """Request body for POST JSONL validation."""

    profile_id: str
    raw_jsonl: str


class JsonlInvalidRecord(BaseModel):
    """Invalid record payload shape returned by JSONL validation."""

    line: int
    error: str
    raw: str
    kind: Literal["json_parse", "not_object", "schema_validation"]


class JsonlValidateMetrics(BaseModel):
    """Validation metrics returned by JSONL validation."""

    total_lines: int
    json_valid_lines: int
    schema_valid_records: int
    invalid_lines: int


class JsonlValidateResponse(BaseModel):
    """HTTP response body for JSONL validation."""

    valid_records: list[dict[str, Any]]
    invalid_records: list[JsonlInvalidRecord]
    metrics: JsonlValidateMetrics


class RunScoreRequest(BaseModel):
    """Request body for POST run."""

    profile_id: str
    records: list[dict[str, Any]]
    require_snapshot: bool = Field(
        default=False,
        description=(
            "If true, snapshot persistence is mandatory. Run fails when snapshot write fails."
        ),
    )


class RunSummary(BaseModel):
    """Internal run summary used by services and API handlers."""

    run_id: str
    profile_id: str
    total: int
    gate_passed: int
    gate_failed: int
    skipped: int
    records: list[dict[str, Any]]
    errors: list[IngestError]
    snapshot_dir: str | None = None
    snapshot_status: Literal["written", "failed"] = "written"
    snapshot_error: str | None = None


class RunResponseMetrics(BaseModel):
    """Response metrics from POST run."""

    loaded: int
    processed: int
    skipped: int
    gate_passed: int
    gate_failed: int
    gate_pass_rate: float
    started_at: str
    finished_at: str


class RunScoreResponse(BaseModel):
    """HTTP response body for POST run."""

    run_id: str
    profile_id: str
    scored_records: list[dict[str, Any]]
    metrics: RunResponseMetrics
    errors: list[dict[str, Any]]
    snapshot_dir: str | None = None
    snapshot_status: Literal["written", "failed"] = "written"
    snapshot_error: str | None = None


class RunValidateChecks(BaseModel):
    """Validation checks executed by dry-run validation for /run."""

    profile_exists: bool
    constraints_valid: bool
    scoring_config_valid: bool
    all_records_schema_valid: bool
    snapshot_io_checked: bool = False
    snapshot_io_writable: bool | None = None


class RunValidateSummary(BaseModel):
    """Dry-run summary for validating whether /run can execute."""

    ok: bool
    profile_id: str
    total_records: int
    valid_records: int
    invalid_records: int
    errors: list[IngestError]
    checks: RunValidateChecks
    snapshot_probe_dir: str | None = None
    snapshot_probe_error: str | None = None


class CandidateSkillSet(BaseModel):
    """External candidate skill shape for gen-cv action."""

    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)


class CandidateExperience(BaseModel):
    """External candidate experience entry for gen-cv action."""

    company: str
    title: str
    duration_months: int | None = None
    highlights: list[str] = Field(default_factory=list)
    stack: list[str] = Field(default_factory=list)


class CandidateInput(BaseModel):
    """External candidate payload for gen-cv action."""

    id: str | None = None
    name: str | None = None
    seniority: str
    tech_stack: CandidateSkillSet | None = None
    experience: list[CandidateExperience] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    spoken_languages: list[str] = Field(default_factory=list)
    location: str | None = None
    timezone: str | None = None
    availability_days: int | None = None
    role_focus: list[str] = Field(default_factory=list)


class GenCVRequest(BaseModel):
    """Request body for POST /v1/tasks/{task_id}/actions/gen-cv."""

    profile_id: str
    job: dict[str, Any]
    candidate_profile: CandidateInput
    selected_claim_ids: list[str] | None = None
    llm_model: str | None = Field(default=None)
    allow_mock_fallback: bool = True


class GenCVResponse(BaseModel):
    """Response body for gen-cv action."""

    cv_markdown: str
    generated_cv_json: dict[str, Any] | None = None
    model_info: dict[str, Any] | None = None
