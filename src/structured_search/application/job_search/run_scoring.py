"""Application use-case for deterministic scoring and snapshot persistence."""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from structured_search.application.common.dependencies import (
    ApplicationDependencies,
    resolve_dependencies,
)
from structured_search.application.common.errors import SnapshotPersistenceError
from structured_search.application.job_search.profiles import bundle_to_data, load_bundle
from structured_search.contracts import (
    IngestError,
    ProfileBundle,
    RunScoreRequest,
    RunSummary,
    RunValidateChecks,
    RunValidateSummary,
)
from structured_search.infra.config_loader import task_json_to_scoring_config
from structured_search.infra.scoring import HeuristicScorer
from structured_search.tasks.job_search.models import JobPosting, JobSearchConstraints

logger = logging.getLogger(__name__)


def _make_run_id(profile_id: str) -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    short = uuid.uuid4().hex[:6]
    return f"{profile_id}-{ts}-{short}"


def run_score(
    request: RunScoreRequest,
    deps: ApplicationDependencies | None = None,
) -> RunSummary:
    """Validate records, score them and write run snapshot metadata."""
    resolved = resolve_dependencies(deps)
    bundle = load_bundle(request.profile_id, deps=resolved)
    constraints, scorer = _build_scorer_components(bundle)
    valid_postings, schema_errors = _validate_records(request.records)

    skipped = len(schema_errors)
    scored_records: list[dict[str, Any]] = []
    gate_passed = 0
    gate_failed = 0

    for posting in valid_postings:
        scored = scorer.score(posting, constraints)
        scored_dict = scored.model_dump(mode="json")
        scored_records.append(scored_dict)

        if scored.gate_passed:
            gate_passed += 1
        else:
            gate_failed += 1

    run_id = _make_run_id(request.profile_id)
    snapshot = resolved.run_repo.save_snapshot(
        run_id=run_id,
        bundle=bundle_to_data(bundle),
        input_records=request.records,
        output_records=scored_records,
        meta={
            "run_id": run_id,
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
    request: RunScoreRequest,
    deps: ApplicationDependencies | None = None,
) -> RunValidateSummary:
    """Dry-run validation for /run without real scoring execution."""
    resolved = resolve_dependencies(deps)
    bundle = load_bundle(request.profile_id, deps=resolved)
    _build_scorer_components(bundle)
    valid_postings, schema_errors = _validate_records(request.records)
    snapshot_probe = _probe_snapshot_io(
        resolved=resolved,
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
        valid_records=len(valid_postings),
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


def _build_scorer_components(
    bundle: ProfileBundle,
) -> tuple[JobSearchConstraints, HeuristicScorer]:
    """Build scoring constraints and scorer from a profile bundle."""
    constraints = JobSearchConstraints.model_validate(bundle.constraints)
    scoring_config = task_json_to_scoring_config(bundle.task)
    scorer = HeuristicScorer(config=scoring_config)
    return constraints, scorer


def _validate_records(records: list[dict[str, Any]]) -> tuple[list[JobPosting], list[IngestError]]:
    """Validate request records against JobPosting schema."""
    valid_postings: list[JobPosting] = []
    schema_errors: list[IngestError] = []
    for idx, raw in enumerate(records, start=1):
        try:
            posting = JobPosting.model_validate(raw)
        except ValidationError as exc:
            schema_errors.append(
                IngestError(
                    line_no=idx,
                    raw_preview=json.dumps(raw, ensure_ascii=False)[:200],
                    kind="schema_validation",
                    message=exc.errors(include_url=False).__str__(),
                )
            )
            continue
        valid_postings.append(posting)
    return valid_postings, schema_errors


def _probe_snapshot_io(
    *,
    resolved: ApplicationDependencies,
    profile_id: str,
    bundle: ProfileBundle,
    input_records: list[dict[str, Any]],
):
    """Perform a lightweight snapshot write/delete probe used by dry-run validation."""
    run_id = f"_validate-{profile_id}-{uuid.uuid4().hex[:8]}"
    probe = resolved.run_repo.save_snapshot(
        run_id=run_id,
        bundle=bundle_to_data(bundle),
        input_records=input_records,
        output_records=[],
        meta={
            "run_id": run_id,
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
