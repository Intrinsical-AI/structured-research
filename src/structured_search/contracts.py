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


class ProfileBundle(BaseModel):
    """All editable config for one search profile."""

    profile_id: str
    constraints: dict[str, Any]
    task: dict[str, Any]
    task_config: dict[str, Any]
    user_profile: dict[str, Any] | None = None
    domain_schema: dict[str, Any] | None = None
    result_schema: dict[str, Any] | None = None


class ProfileSummary(BaseModel):
    """Summary item from GET /v1/job-search/profiles."""

    id: str
    name: str
    updated_at: str


class BundleSaveResponse(BaseModel):
    """Response from PUT /v1/job-search/profiles/{id}/bundle."""

    valid: bool
    issues: list[ValidationIssue]


class BundleWriteResponse(BaseModel):
    """HTTP response body for PUT /v1/job-search/profiles/{id}/bundle."""

    ok: bool
    version: str | None = None
    errors: list[ValidationIssue] = Field(default_factory=list)


class PromptResponse(BaseModel):
    """Response from POST /v1/job-search/prompt/generate."""

    profile_id: str
    step: str
    prompt: str


class PromptGenerateRequest(BaseModel):
    """Request body for POST /v1/job-search/prompt/generate."""

    profile_id: str
    step: str = "S3_execute"


class PromptGenerateResponse(BaseModel):
    """HTTP response body for POST /v1/job-search/prompt/generate."""

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
    """Response from POST /v1/job-search/jsonl/validate."""

    valid: list[dict[str, Any]]
    invalid: list[IngestError]
    stats: IngestStats


class JsonlValidateRequest(BaseModel):
    """Request body for POST /v1/job-search/jsonl/validate."""

    profile_id: str
    raw_jsonl: str


class JsonlInvalidRecord(BaseModel):
    """Invalid record payload shape returned by /v1/job-search/jsonl/validate."""

    line: int
    error: str
    raw: str
    kind: Literal["json_parse", "not_object", "schema_validation"]


class JsonlValidateMetrics(BaseModel):
    """Validation metrics returned by /v1/job-search/jsonl/validate."""

    total_lines: int
    json_valid_lines: int
    schema_valid_records: int
    invalid_lines: int


class JsonlValidateResponse(BaseModel):
    """HTTP response body for POST /v1/job-search/jsonl/validate."""

    valid_records: list[dict[str, Any]]
    invalid_records: list[JsonlInvalidRecord]
    metrics: JsonlValidateMetrics


class RunScoreRequest(BaseModel):
    """Request body for POST /v1/job-search/run (canonical)."""

    profile_id: str
    records: list[dict[str, Any]]
    require_snapshot: bool = Field(
        default=False,
        description=(
            "If true, snapshot persistence is mandatory. Run fails when snapshot write fails."
        ),
    )


class RunSummary(BaseModel):
    """Internal run summary used by the service and API handlers."""

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
    """Response metrics from POST /v1/job-search/run."""

    loaded: int
    processed: int
    skipped: int
    started_at: str
    finished_at: str


class RunScoreResponse(BaseModel):
    """HTTP response body for POST /v1/job-search/run."""

    run_id: str
    profile_id: str
    scored_records: list[dict[str, Any]]
    metrics: RunResponseMetrics
    errors: list[dict[str, Any]]
    snapshot_dir: str | None = None
    snapshot_status: Literal["written", "failed"] = "written"
    snapshot_error: str | None = None


class RunValidateChecks(BaseModel):
    """Validation checks executed by dry-run validation for /v1/job-search/run."""

    profile_exists: bool
    constraints_valid: bool
    scoring_config_valid: bool
    all_records_schema_valid: bool
    snapshot_io_checked: bool = False
    snapshot_io_writable: bool | None = None


class RunValidateSummary(BaseModel):
    """Dry-run summary for validating whether /v1/job-search/run can execute."""

    ok: bool
    profile_id: str
    total_records: int
    valid_records: int
    invalid_records: int
    errors: list[IngestError]
    checks: RunValidateChecks
    snapshot_probe_dir: str | None = None
    snapshot_probe_error: str | None = None


class CvSkillSetInput(BaseModel):
    """External candidate skill shape for POST /v1/gen-cv."""

    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)


class CvExperienceInput(BaseModel):
    """External candidate experience entry for POST /v1/gen-cv."""

    company: str
    title: str
    duration_months: int | None = None
    highlights: list[str] = Field(default_factory=list)
    stack: list[str] = Field(default_factory=list)


class CvCandidateInput(BaseModel):
    """External candidate payload for POST /v1/gen-cv."""

    id: str | None = None
    name: str | None = None
    seniority: str
    tech_stack: CvSkillSetInput | None = None
    experience: list[CvExperienceInput] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    spoken_languages: list[str] = Field(default_factory=list)
    location: str | None = None
    timezone: str | None = None
    availability_days: int | None = None
    role_focus: list[str] = Field(default_factory=list)


class GenCVRequest(BaseModel):
    """Request body for POST /v1/gen-cv."""

    profile_id: str
    job: dict[str, Any]
    candidate_profile: CvCandidateInput
    selected_claim_ids: list[str] | None = None
    llm_model: str | None = Field(default=None)
    allow_mock_fallback: bool = True


class GenCVResponse(BaseModel):
    """Response from POST /v1/gen-cv."""

    cv_markdown: str
    generated_cv_json: dict[str, Any] | None = None
    model_info: dict[str, Any] | None = None
