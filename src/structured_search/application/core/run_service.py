"""Generic deterministic scoring + snapshot persistence for task plugins."""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from structured_search.application.common.dependencies import (
    ApplicationDependencies,
    resolve_dependencies,
)
from structured_search.application.common.errors import SnapshotPersistenceError
from structured_search.application.common.validation_messages import format_schema_validation_error
from structured_search.application.core.bundle_service import bundle_to_data, load_bundle
from structured_search.application.core.task_plugin import BuildRuntimeFn, TaskPlugin
from structured_search.contracts import (
    IngestError,
    RunScoreRequest,
    RunSummary,
    RunValidateChecks,
    RunValidateSummary,
)

logger = logging.getLogger(__name__)


def _make_run_id(task_id: str, profile_id: str) -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    short = uuid.uuid4().hex[:6]
    return f"{task_id}-{profile_id}-{ts}-{short}"


def _require_plugin_runtime(plugin: TaskPlugin) -> tuple[BuildRuntimeFn, type[BaseModel]]:
    if plugin.build_runtime is None or plugin.record_model is None:
        raise ValueError(f"Task {plugin.task_id!r} does not support scoring runtime")
    return plugin.build_runtime, plugin.record_model


def _validate_records(
    records: list[dict[str, Any]],
    *,
    record_model: type[BaseModel],
) -> tuple[list[Any], list[IngestError]]:
    valid: list[Any] = []
    schema_errors: list[IngestError] = []
    for idx, raw in enumerate(records, start=1):
        try:
            posting = record_model.model_validate(raw)
        except ValidationError as exc:
            schema_errors.append(
                IngestError(
                    line_no=idx,
                    raw_preview=json.dumps(raw, ensure_ascii=False)[:200],
                    kind="schema_validation",
                    message=format_schema_validation_error(exc),
                )
            )
            continue
        valid.append(posting)
    return valid, schema_errors


def run_score(
    *,
    task_id: str,
    request: RunScoreRequest,
    plugin: TaskPlugin,
    deps: ApplicationDependencies | None = None,
) -> RunSummary:
    build_runtime, record_model = _require_plugin_runtime(plugin)

    resolved = resolve_dependencies(deps)
    bundle = load_bundle(task_id=task_id, profile_id=request.profile_id, deps=resolved)
    constraints, scorer = build_runtime(bundle.constraints, bundle.task)
    valid_records, schema_errors = _validate_records(
        request.records,
        record_model=record_model,
    )

    skipped = len(schema_errors)
    scored_records: list[dict[str, Any]] = []
    gate_passed = 0
    gate_failed = 0

    for record in valid_records:
        scored = scorer.score(record, constraints)
        scored_dict = scored.model_dump(mode="json")
        scored_records.append(scored_dict)
        if scored.gate_passed:
            gate_passed += 1
        else:
            gate_failed += 1

    run_id = _make_run_id(task_id=task_id, profile_id=request.profile_id)
    snapshot = resolved.run_repo.save_snapshot(
        run_id=run_id,
        bundle=bundle_to_data(bundle),
        input_records=request.records,
        output_records=scored_records,
        meta={
            "run_id": run_id,
            "task_id": task_id,
            "profile_id": request.profile_id,
            "total": len(request.records),
            "gate_passed": gate_passed,
            "gate_failed": gate_failed,
            "skipped": skipped,
        },
    )

    if snapshot.status == "failed":
        logger.warning(
            "Could not write run snapshot to %s: %s",
            snapshot.snapshot_dir,
            snapshot.error,
        )
        if request.require_snapshot:
            raise SnapshotPersistenceError(
                f"snapshot write failed for run {run_id}: {snapshot.error}"
            )

    return RunSummary(
        run_id=run_id,
        profile_id=request.profile_id,
        total=len(request.records),
        gate_passed=gate_passed,
        gate_failed=gate_failed,
        skipped=skipped,
        records=scored_records,
        errors=schema_errors,
        snapshot_dir=snapshot.snapshot_dir if snapshot.status == "written" else None,
        snapshot_status=snapshot.status,
        snapshot_error=snapshot.error,
    )


def validate_run(
    *,
    task_id: str,
    request: RunScoreRequest,
    plugin: TaskPlugin,
    deps: ApplicationDependencies | None = None,
) -> RunValidateSummary:
    build_runtime, record_model = _require_plugin_runtime(plugin)

    resolved = resolve_dependencies(deps)

    try:
        bundle = load_bundle(task_id=task_id, profile_id=request.profile_id, deps=resolved)
    except FileNotFoundError:
        return RunValidateSummary(
            ok=False,
            profile_id=request.profile_id,
            total_records=len(request.records),
            valid_records=0,
            invalid_records=0,
            errors=[],
            checks=RunValidateChecks(
                profile_exists=False,
                constraints_valid=False,
                scoring_config_valid=False,
                all_records_schema_valid=False,
                snapshot_io_checked=False,
            ),
        )

    # Step 1: validate constraints payload shape independently.
    if plugin.constraints_model is not None:
        try:
            plugin.constraints_model.model_validate(bundle.constraints)
        except (ValueError, ValidationError):
            return RunValidateSummary(
                ok=False,
                profile_id=request.profile_id,
                total_records=len(request.records),
                valid_records=0,
                invalid_records=0,
                errors=[],
                checks=RunValidateChecks(
                    profile_exists=True,
                    constraints_valid=False,
                    scoring_config_valid=False,
                    all_records_schema_valid=False,
                    snapshot_io_checked=False,
                ),
            )

    # Step 2: build full runtime — isolates scoring config failures from constraints.
    # If this raises after step 1 passed, the problem is in task/scoring config.
    try:
        _ = build_runtime(bundle.constraints, bundle.task)
    except (ValueError, ValidationError):
        return RunValidateSummary(
            ok=False,
            profile_id=request.profile_id,
            total_records=len(request.records),
            valid_records=0,
            invalid_records=0,
            errors=[],
            checks=RunValidateChecks(
                profile_exists=True,
                constraints_valid=True,
                scoring_config_valid=False,
                all_records_schema_valid=False,
                snapshot_io_checked=False,
            ),
        )

    valid_records, schema_errors = _validate_records(
        request.records,
        record_model=record_model,
    )

    snapshot_probe = _probe_snapshot_io(
        resolved=resolved,
        task_id=task_id,
        profile_id=request.profile_id,
        bundle=bundle,
        input_records=request.records,
    )
    snapshot_io_writable = snapshot_probe.status == "written"
    can_run = snapshot_io_writable or not request.require_snapshot

    return RunValidateSummary(
        ok=can_run,
        profile_id=request.profile_id,
        total_records=len(request.records),
        valid_records=len(valid_records),
        invalid_records=len(schema_errors),
        errors=schema_errors,
        checks=RunValidateChecks(
            profile_exists=True,
            constraints_valid=True,
            scoring_config_valid=True,
            all_records_schema_valid=not schema_errors,
            snapshot_io_checked=True,
            snapshot_io_writable=snapshot_io_writable,
        ),
        snapshot_probe_dir=snapshot_probe.snapshot_dir,
        snapshot_probe_error=snapshot_probe.error,
    )


def _probe_snapshot_io(
    *,
    resolved: ApplicationDependencies,
    task_id: str,
    profile_id: str,
    bundle,
    input_records: list[dict[str, Any]],
):
    run_id = f"_validate-{task_id}-{profile_id}-{uuid.uuid4().hex[:8]}"
    probe = resolved.run_repo.save_snapshot(
        run_id=run_id,
        bundle=bundle_to_data(bundle),
        input_records=input_records,
        output_records=[],
        meta={
            "run_id": run_id,
            "task_id": task_id,
            "profile_id": profile_id,
            "probe": True,
        },
    )
    _cleanup_probe_snapshot_dir(probe.snapshot_dir)
    return probe


def _cleanup_probe_snapshot_dir(snapshot_dir: str | None) -> None:
    if not snapshot_dir:
        return
    path = Path(snapshot_dir)
    if not path.exists():
        return
    try:
        shutil.rmtree(path)
    except Exception as exc:
        logger.warning("Could not clean up dry-run snapshot probe dir '%s': %s", path, exc)
