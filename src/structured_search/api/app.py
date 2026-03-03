"""FastAPI application exposing structured-search HTTP endpoints."""

from __future__ import annotations

import hashlib
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from structured_search.application.common.dependencies import (
    clear_configured_dependencies,
    configure_filesystem_dependencies,
)
from structured_search.application.common.metrics import emit_q2_metric_event
from structured_search.application.gen_cv.generate_cv import gen_cv
from structured_search.application.job_search.ingest import ingest_validate_jsonl
from structured_search.application.job_search.profiles import (
    list_profiles,
    load_bundle,
    save_bundle,
)
from structured_search.application.job_search.prompts import generate_prompt
from structured_search.application.job_search.run_scoring import run_score, validate_run
from structured_search.contracts import (
    BundleSaveResponse,
    BundleWriteResponse,
    GenCVRequest,
    GenCVResponse,
    JsonlValidateRequest,
    JsonlValidateResponse,
    ProfileBundle,
    ProfileSummary,
    PromptGenerateRequest,
    PromptGenerateResponse,
    RunScoreRequest,
    RunScoreResponse,
    RunValidateSummary,
)

logger = logging.getLogger(__name__)

_PROFILES_BASE = Path("config/job_search")
_PROMPTS_DIR = Path("resources/prompts")
_RUNS_DIR = Path("runs")


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Wire explicit dependencies for the whole API process lifecycle."""
    configure_filesystem_dependencies(
        profiles_base=_PROFILES_BASE,
        runs_dir=_RUNS_DIR,
        prompts_dir=_PROMPTS_DIR,
    )
    try:
        yield
    finally:
        clear_configured_dependencies()


app = FastAPI(
    title="structured-search API",
    version="0.2.0",
    description="HTTP API for structured, auditable search workflows.",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _emit_metric_event(event_type: str, **fields: Any) -> None:
    try:
        emit_q2_metric_event(event_type, **fields)
        logger.info("metric_event", extra={"event_type": event_type, **fields})
    except Exception as exc:
        logger.warning("Failed to emit metric event '%s': %s", event_type, exc)


@app.get(
    "/v1/job-search/profiles",
    response_model=list[ProfileSummary],
    summary="List available job_search profiles",
)
def get_profiles() -> list[ProfileSummary]:
    return list_profiles()


@app.get(
    "/v1/job-search/profiles/{profile_id}/bundle",
    response_model=ProfileBundle,
    summary="Load a profile bundle (constraints + task + task_config + optional sections)",
)
def get_bundle(profile_id: str) -> ProfileBundle:
    try:
        return load_bundle(profile_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put(
    "/v1/job-search/profiles/{profile_id}/bundle",
    response_model=BundleWriteResponse,
    summary="Validate and save a profile bundle",
)
def put_bundle(profile_id: str, bundle: ProfileBundle) -> dict[str, Any]:
    bundle.profile_id = profile_id
    result: BundleSaveResponse = save_bundle(bundle)
    if result.valid:
        return BundleWriteResponse(
            ok=True,
            version=datetime.now(UTC).isoformat(),
            errors=result.issues,
        ).model_dump(mode="json")
    return BundleWriteResponse(ok=False, errors=result.issues).model_dump(mode="json")


@app.post(
    "/v1/job-search/prompt/generate",
    response_model=PromptGenerateResponse,
    summary="Compose an extraction prompt for a profile and step",
)
def post_generate_prompt(request: PromptGenerateRequest) -> dict[str, Any]:
    try:
        result = generate_prompt(request.profile_id, request.step)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    prompt_hash = f"sha256:{hashlib.sha256(result.prompt.encode('utf-8')).hexdigest()}"
    response = PromptGenerateResponse(
        profile_id=request.profile_id,
        step=request.step,
        prompt=result.prompt,
        constraints_embedded="## Search Constraints" in result.prompt,
        prompt_hash=prompt_hash,
    )
    return response.model_dump(mode="json")


@app.post(
    "/v1/job-search/jsonl/validate",
    response_model=JsonlValidateResponse,
    summary="Parse JSONL tolerantly and validate records against JobPosting schema",
)
def post_jsonl_validate(request: JsonlValidateRequest) -> dict[str, Any]:
    result = ingest_validate_jsonl(request.raw_jsonl)
    invalid_records = [
        {
            "line": err.line_no,
            "error": err.message,
            "raw": err.raw_preview,
            "kind": err.kind,
        }
        for err in result.invalid
    ]
    response = JsonlValidateResponse(
        valid_records=result.valid,
        invalid_records=invalid_records,
        metrics={
            "total_lines": result.stats.total_lines,
            "json_valid_lines": result.stats.parse_ok,
            "schema_valid_records": result.stats.schema_ok,
            "invalid_lines": result.stats.parse_errors + result.stats.schema_errors,
        },
    )

    total_lines = response.metrics.total_lines
    parse_errors = result.stats.parse_errors
    _emit_metric_event(
        "job_search_jsonl_validate",
        profile_id=request.profile_id,
        total_lines=total_lines,
        parse_errors=parse_errors,
        parse_error_ratio=(parse_errors / total_lines) if total_lines else 0.0,
    )
    return response.model_dump(mode="json")


@app.post(
    "/v1/job-search/run/validate",
    response_model=RunValidateSummary,
    summary="Dry-run validation for /run prerequisites without scoring",
    responses={
        404: {"description": "Profile not found"},
        422: {"description": "Validation/config error in request or profile task"},
    },
)
def post_run_validate(request: RunScoreRequest) -> RunValidateSummary:
    try:
        result = validate_run(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@app.post(
    "/v1/job-search/run",
    response_model=RunScoreResponse,
    summary="Score pre-validated records using profile task config",
    responses={
        404: {"description": "Profile not found"},
        422: {"description": "Validation/config error in request or profile task"},
        500: {"description": "Run failed (e.g. required snapshot write failure)"},
    },
)
def post_run(request: RunScoreRequest) -> dict[str, Any]:
    started_at = datetime.now(UTC)
    started_clock = perf_counter()
    try:
        result = run_score(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finished_at = datetime.now(UTC)
    latency_ms = round((perf_counter() - started_clock) * 1000, 3)

    _emit_metric_event(
        "job_search_run",
        profile_id=result.profile_id,
        run_id=result.run_id,
        latency_ms=latency_ms,
        snapshot_status=result.snapshot_status,
        require_snapshot=request.require_snapshot,
    )

    response = RunScoreResponse(
        run_id=result.run_id,
        profile_id=result.profile_id,
        scored_records=result.records,
        metrics={
            "loaded": result.total,
            "processed": len(result.records),
            "skipped": result.skipped,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
        },
        errors=[e.model_dump(mode="json") for e in result.errors],
        snapshot_dir=result.snapshot_dir,
        snapshot_status=result.snapshot_status,
        snapshot_error=result.snapshot_error,
    )
    return response.model_dump(mode="json")


@app.post(
    "/v1/gen-cv",
    response_model=GenCVResponse,
    summary="Generate a CV markdown and structured JSON",
    responses={
        404: {"description": "Profile not found"},
        422: {"description": "Validation error in request payload"},
        503: {"description": "CV provider unavailable"},
    },
)
def post_gen_cv(request: GenCVRequest) -> GenCVResponse:
    try:
        response = gen_cv(
            profile_id=request.profile_id,
            job=request.job,
            candidate_profile=request.candidate_profile,
            selected_claim_ids=request.selected_claim_ids,
            llm_model=request.llm_model,
            allow_mock_fallback=request.allow_mock_fallback,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    fallback_used = bool((response.model_info or {}).get("fallback_used"))
    _emit_metric_event(
        "gen_cv",
        profile_id=request.profile_id,
        fallback_used=fallback_used,
        llm_model=request.llm_model,
    )
    return response


def main() -> None:
    import uvicorn

    uvicorn.run("structured_search.api.app:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
