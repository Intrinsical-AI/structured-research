"""Application use-cases for profile discovery and bundle persistence."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from structured_search.application.common.dependencies import (
    ApplicationDependencies,
    resolve_dependencies,
)
from structured_search.contracts import (
    BundleSaveResponse,
    ProfileBundle,
    ValidationIssue,
)
from structured_search.infra.config_loader import TaskRuntimeConfig, collect_model_field_paths
from structured_search.ports.persistence import BundleData
from structured_search.tasks.job_search.models import JobPosting, JobSearchConstraints

# Computed once from JobPosting and reused for cross-field warnings.
POSTING_VALID_PATHS: frozenset[str] = collect_model_field_paths(JobPosting)


def bundle_from_data(profile_id: str, data: BundleData) -> ProfileBundle:
    return ProfileBundle(
        profile_id=profile_id,
        constraints=data.constraints,
        task=data.task,
        task_config=data.task_config,
        user_profile=data.user_profile,
        domain_schema=data.domain_schema,
        result_schema=data.result_schema,
    )


def bundle_to_data(bundle: ProfileBundle) -> BundleData:
    return BundleData(
        constraints=bundle.constraints,
        task=bundle.task,
        task_config=bundle.task_config,
        user_profile=bundle.user_profile,
        domain_schema=bundle.domain_schema,
        result_schema=bundle.result_schema,
    )


def extract_profile_name(profile_id: str, user_profile: dict[str, Any] | None) -> str:
    if isinstance(user_profile, dict):
        role_focus = user_profile.get("role_focus")
        if isinstance(role_focus, list) and role_focus and isinstance(role_focus[0], str):
            return role_focus[0]
        name = user_profile.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return profile_id


def list_profiles(deps: ApplicationDependencies | None = None) -> list[dict[str, str]]:
    """Discover available profile IDs under config/job_search."""
    resolved = resolve_dependencies(deps)
    result: list[dict[str, str]] = []
    for profile in resolved.profile_repo.list_profiles():
        result.append(
            {
                "id": profile.id,
                "name": extract_profile_name(profile.id, profile.user_profile),
                "updated_at": profile.updated_at,
            }
        )
    return result


def load_bundle(
    profile_id: str,
    deps: ApplicationDependencies | None = None,
) -> ProfileBundle:
    """Read constraints, task and task_config from profile bundle.json."""
    resolved = resolve_dependencies(deps)
    data = resolved.profile_repo.load_bundle(profile_id)
    return bundle_from_data(profile_id, data)


def _append_validation_errors(
    issues: list[ValidationIssue],
    *,
    prefix: str,
    exc: ValidationError,
) -> None:
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"])
        path = f"{prefix}.{loc}" if loc else prefix
        issues.append(
            ValidationIssue(
                path=path,
                code=err["type"],
                message=err["msg"],
                severity="error",
            )
        )


def _validate_constraints(bundle: ProfileBundle, issues: list[ValidationIssue]) -> None:
    try:
        JobSearchConstraints.model_validate(bundle.constraints)
    except ValidationError as exc:
        _append_validation_errors(issues, prefix="constraints", exc=exc)


def _validate_task_sections(bundle: ProfileBundle, issues: list[ValidationIssue]) -> bool:
    has_required_sections = True
    for required_key in ("gates", "soft_scoring"):
        if required_key in bundle.task:
            continue
        has_required_sections = False
        issues.append(
            ValidationIssue(
                path=f"task.{required_key}",
                code="required_field_missing",
                message=f"task must contain '{required_key}'",
                severity="error",
            )
        )
    return has_required_sections


def _validate_task_config_type(bundle: ProfileBundle, issues: list[ValidationIssue]) -> None:
    if isinstance(bundle.task_config, dict):
        return
    issues.append(
        ValidationIssue(
            path="task_config",
            code="invalid_type",
            message="task_config must be a JSON object",
            severity="error",
        )
    )


def _validate_task_runtime(bundle: ProfileBundle, issues: list[ValidationIssue]) -> None:
    try:
        TaskRuntimeConfig.model_validate(bundle.task)
    except ValidationError as exc:
        _append_validation_errors(issues, prefix="task", exc=exc)


def _append_unknown_field_warnings(
    issues: list[ValidationIssue],
    *,
    rules: list[Any],
    path_prefix: str,
    message_suffix: str,
) -> None:
    for idx, rule in enumerate(rules):
        field_path: str = rule.get("field", "") if isinstance(rule, dict) else ""
        if field_path and field_path not in POSTING_VALID_PATHS:
            issues.append(
                ValidationIssue(
                    path=f"{path_prefix}[{idx}].field",
                    code="unknown_field_path",
                    message=(
                        f"'{field_path}' is not a declared field on JobPosting — {message_suffix}"
                    ),
                    severity="warning",
                )
            )


def _append_rule_warnings(bundle: ProfileBundle, issues: list[ValidationIssue]) -> None:
    _append_unknown_field_warnings(
        issues,
        rules=bundle.constraints.get("must", []),
        path_prefix="constraints.must",
        message_suffix="the scorer will score 0 for this rule",
    )
    _append_unknown_field_warnings(
        issues,
        rules=bundle.constraints.get("prefer", []),
        path_prefix="constraints.prefer",
        message_suffix="the scorer will score 0 for this rule",
    )
    _append_unknown_field_warnings(
        issues,
        rules=bundle.constraints.get("avoid", []),
        path_prefix="constraints.avoid",
        message_suffix="the scorer will score 0 for this rule",
    )
    hard_filters = (
        bundle.task.get("gates", {}).get("hard_filters", [])
        if isinstance(bundle.task.get("gates"), dict)
        else []
    )
    _append_unknown_field_warnings(
        issues,
        rules=hard_filters if isinstance(hard_filters, list) else [],
        path_prefix="task.gates.hard_filters",
        message_suffix="this hard filter may never match and can distort gating",
    )


def save_bundle(
    bundle: ProfileBundle,
    deps: ApplicationDependencies | None = None,
) -> BundleSaveResponse:
    """Validate and persist a ProfileBundle to disk with warning/error split."""
    issues: list[ValidationIssue] = []
    _validate_constraints(bundle, issues)
    task_has_required_sections = _validate_task_sections(bundle, issues)
    _validate_task_config_type(bundle, issues)
    if task_has_required_sections:
        _validate_task_runtime(bundle, issues)

    if any(i.severity == "error" for i in issues):
        return BundleSaveResponse(valid=False, issues=issues)
    _append_rule_warnings(bundle, issues)

    resolved = resolve_dependencies(deps)
    resolved.profile_repo.save_bundle(bundle.profile_id, bundle_to_data(bundle))

    return BundleSaveResponse(valid=True, issues=issues)
