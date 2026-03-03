"""FastAPI application exposing task-scoped structured-search HTTP endpoints."""

from __future__ import annotations

import hashlib
import logging
import os
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
from structured_search.application.core.bundle_service import (
    list_profiles,
    load_bundle,
    save_bundle,
)
from structured_search.application.core.ingest_service import ingest_validate_jsonl
from structured_search.application.core.prompt_service import generate_prompt
from structured_search.application.core.run_service import run_score, validate_run
from structured_search.application.core.task_registry import get_task_registry
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
    TaskSummary,
)

logger = logging.getLogger(__name__)

_PROFILES_BASE = Path(os.getenv("PROFILES_BASE", "config"))
_PROMPTS_DIR = Path("resources/prompts")
_RUNS_DIR = Path("runs")


@asynccontextmanager
async def _lifespan(_app: FastAPI):
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
    version="0.3.0",
    description="Task-scoped HTTP API for structured, auditable search workflows.",
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


def _resolve_plugin(task_id: str):
    registry = get_task_registry()
    try:
        return registry.get(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _require_capability(task_id: str, capability: str):
    plugin = _resolve_plugin(task_id)
    if not plugin.supports(capability):
        raise HTTPException(
            status_code=422,
            detail=f"Task {task_id!r} does not support capability {capability!r}",
        )
    return plugin


@app.get("/v1/tasks", response_model=list[TaskSummary], summary="List registered tasks")
def get_tasks() -> list[TaskSummary]:
    return get_task_registry().list()


@app.get(
    "/v1/tasks/{task_id}/profiles",
    response_model=list[ProfileSummary],
    summary="List available profiles for one task",
)
def get_profiles(task_id: str) -> list[ProfileSummary]:
    _resolve_plugin(task_id)
    return [ProfileSummary.model_validate(item) for item in list_profiles(task_id=task_id)]


@app.get(
    "/v1/tasks/{task_id}/profiles/{profile_id}/bundle",
    response_model=ProfileBundle,
    summary="Load a task/profile bundle",
)
def get_bundle(task_id: str, profile_id: str) -> ProfileBundle:
    _resolve_plugin(task_id)
    try:
        return load_bundle(task_id=task_id, profile_id=profile_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put(
    "/v1/tasks/{task_id}/profiles/{profile_id}/bundle",
    response_model=BundleWriteResponse,
    summary="Validate and save a task/profile bundle",
)
def put_bundle(task_id: str, profile_id: str, bundle: ProfileBundle) -> dict[str, Any]:
    plugin = _resolve_plugin(task_id)
    bundle.task_id = task_id
    bundle.profile_id = profile_id
    result: BundleSaveResponse = save_bundle(
        task_id=task_id,
        profile_id=profile_id,
        bundle=bundle,
        plugin=plugin,
    )
    if result.valid:
        return BundleWriteResponse(
            ok=True,
            version=datetime.now(UTC).isoformat(),
            errors=result.issues,
        ).model_dump(mode="json")
    return BundleWriteResponse(ok=False, errors=result.issues).model_dump(mode="json")


@app.post(
    "/v1/tasks/{task_id}/prompt/generate",
    response_model=PromptGenerateResponse,
    summary="Compose an extraction prompt for a task/profile and step",
)
def post_generate_prompt(task_id: str, request: PromptGenerateRequest) -> dict[str, Any]:
    plugin = _require_capability(task_id, "prompt")
    try:
        result = generate_prompt(
            task_id=task_id,
            profile_id=request.profile_id,
            step=request.step,
            plugin=plugin,
        )
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
    "/v1/tasks/{task_id}/jsonl/validate",
    response_model=JsonlValidateResponse,
    summary="Parse JSONL tolerantly and validate records against task schema",
)
def post_jsonl_validate(task_id: str, request: JsonlValidateRequest) -> dict[str, Any]:
    plugin = _require_capability(task_id, "jsonl_validate")
    if plugin.record_model is None:
        raise HTTPException(status_code=422, detail=f"Task {task_id!r} has no record model")

    result = ingest_validate_jsonl(raw_text=request.raw_jsonl, record_model=plugin.record_model)
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
        "task_jsonl_validate",
        task_id=task_id,
        profile_id=request.profile_id,
        total_lines=total_lines,
        parse_errors=parse_errors,
        parse_error_ratio=(parse_errors / total_lines) if total_lines else 0.0,
    )
    return response.model_dump(mode="json")


@app.post(
    "/v1/tasks/{task_id}/run/validate",
    response_model=RunValidateSummary,
    summary="Dry-run validation for run prerequisites without scoring",
    responses={
        404: {"description": "Task/profile not found"},
        422: {"description": "Validation/config error"},
    },
)
def post_task_run_validate(
    task_id: str,
    request: RunScoreRequest,
) -> RunValidateSummary:
    plugin = _require_capability(task_id, "run")
    try:
        return validate_run(task_id=task_id, request=request, plugin=plugin)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post(
    "/v1/tasks/{task_id}/run",
    response_model=RunScoreResponse,
    summary="Score pre-validated records using task profile runtime config",
    responses={
        404: {"description": "Task/profile not found"},
        422: {"description": "Validation/config error"},
        500: {"description": "Run failed"},
    },
)
def post_task_run(
    task_id: str,
    request: RunScoreRequest,
) -> dict[str, Any]:
    plugin = _require_capability(task_id, "run")

    started_at = datetime.now(UTC)
    started_clock = perf_counter()
    try:
        result = run_score(task_id=task_id, request=request, plugin=plugin)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finished_at = datetime.now(UTC)
    latency_ms = round((perf_counter() - started_clock) * 1000, 3)

    _emit_metric_event(
        "task_run",
        task_id=task_id,
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
            "gate_passed": result.gate_passed,
            "gate_failed": result.gate_failed,
            "gate_pass_rate": (
                (result.gate_passed / len(result.records)) if result.records else 0.0
            ),
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
    "/v1/tasks/{task_id}/actions/gen-cv",
    response_model=GenCVResponse,
    summary="Generate a CV markdown and structured JSON",
    responses={
        404: {"description": "Task/profile not found"},
        422: {"description": "Validation error in request payload"},
        503: {"description": "CV provider unavailable"},
    },
)
def post_action_gen_cv(task_id: str, request: GenCVRequest) -> GenCVResponse:
    plugin = _require_capability(task_id, "action:gen-cv")
    handler = plugin.action_handlers.get("gen-cv")
    if handler is None:
        raise HTTPException(
            status_code=422,
            detail=f"Task {task_id!r} does not expose action 'gen-cv'",
        )
    try:
        response = handler(
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
        task_id=task_id,
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
