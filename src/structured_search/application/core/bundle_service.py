"""Generic profile bundle use-cases parameterized by task plugins."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError

from structured_search.application.common.dependencies import (
    ApplicationDependencies,
    resolve_dependencies,
)
from structured_search.application.common.model_utils import collect_model_field_paths
from structured_search.application.core.task_plugin import TaskPlugin
from structured_search.contracts import BundleSaveResponse, ProfileBundle, ValidationIssue
from structured_search.ports.persistence import BundleData


def bundle_from_data(task_id: str, profile_id: str, data: BundleData) -> ProfileBundle:
    return ProfileBundle(
        task_id=task_id,
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


def list_profiles(
    task_id: str,
    deps: ApplicationDependencies | None = None,
) -> list[dict[str, str]]:
    resolved = resolve_dependencies(deps)
    result: list[dict[str, str]] = []
    for profile in resolved.profile_repo.list_profiles(task_id):
        result.append(
            {
                "id": profile.id,
                "name": extract_profile_name(profile.id, profile.user_profile),
                "updated_at": profile.updated_at,
            }
        )
    return result


def load_bundle(
    task_id: str,
    profile_id: str,
    deps: ApplicationDependencies | None = None,
) -> ProfileBundle:
    resolved = resolve_dependencies(deps)
    data = resolved.profile_repo.load_bundle(task_id, profile_id)
    return bundle_from_data(task_id, profile_id, data)


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


def _validate_payload_type(
    *,
    model_cls: type[BaseModel] | None,
    value: dict[str, Any],
    prefix: str,
    issues: list[ValidationIssue],
) -> None:
    if model_cls is None:
        return
    try:
        model_cls.model_validate(value)
    except ValidationError as exc:
        _append_validation_errors(issues, prefix=prefix, exc=exc)


def _validate_task_field_paths(
    bundle: ProfileBundle, plugin: TaskPlugin, issues: list[ValidationIssue]
) -> None:
    """Warn when penalty/signal field paths don't exist on the record model."""
    record_model = plugin.record_model
    if record_model is None:
        return

    try:
        task_cfg = TaskRuntimeConfig.model_validate(bundle.task)
    except Exception:
        return  # structural errors already captured by _validate_task_runtime

    valid_paths = collect_model_field_paths(record_model)

    def _warn_if_unknown(field_path: str, json_path: str) -> None:
        if field_path and field_path not in valid_paths:
            issues.append(
                ValidationIssue(
                    path=json_path,
                    code="unknown_field_path",
                    message=(
                        f"'{field_path}' is not a declared field on record model — "
                        "this path will always resolve to missing"
                    ),
                    severity="warning",
                )
            )

    ss = task_cfg.soft_scoring
    _warn_if_unknown(
        ss.signal_boost.salary_field,
        "task.soft_scoring.signal_boost.salary_field",
    )
    _warn_if_unknown(
        ss.penalties.old_posting.field,
        "task.soft_scoring.penalties.old_posting.field",
    )
    _warn_if_unknown(
        ss.penalties.excess_hybrid_days.field,
        "task.soft_scoring.penalties.excess_hybrid_days.field",
    )


def _validate_task_runtime(
    bundle: ProfileBundle, plugin: TaskPlugin, issues: list[ValidationIssue]
) -> None:
    if not plugin.validate_task_runtime:
        return

    for required_key in ("gates", "soft_scoring"):
        if required_key in bundle.task:
            continue
        issues.append(
            ValidationIssue(
                path=f"task.{required_key}",
                code="required_field_missing",
                message=f"task must contain '{required_key}'",
                severity="error",
            )
        )

    _validate_payload_type(
        model_cls=plugin.task_runtime_model,
        value=bundle.task,
        prefix="task",
        issues=issues,
    )


def _append_unknown_field_warnings(
    issues: list[ValidationIssue],
    *,
    rules: list[Any],
    path_prefix: str,
    message_suffix: str,
    valid_paths: frozenset[str],
) -> None:
    for idx, rule in enumerate(rules):
        field_path: str = rule.get("field", "") if isinstance(rule, dict) else ""
        if field_path and field_path not in valid_paths:
            issues.append(
                ValidationIssue(
                    path=f"{path_prefix}[{idx}].field",
                    code="unknown_field_path",
                    message=(
                        f"'{field_path}' is not a declared field on record model — {message_suffix}"
                    ),
                    severity="warning",
                )
            )


def _append_rule_warnings(
    bundle: ProfileBundle, plugin: TaskPlugin, issues: list[ValidationIssue]
) -> None:
    record_model = plugin.record_model
    if record_model is None:
        return
    valid_paths = collect_model_field_paths(record_model)

    _append_unknown_field_warnings(
        issues,
        rules=bundle.constraints.get("must", []),
        path_prefix="constraints.must",
        message_suffix="the scorer will score 0 for this rule",
        valid_paths=valid_paths,
    )
    _append_unknown_field_warnings(
        issues,
        rules=bundle.constraints.get("prefer", []),
        path_prefix="constraints.prefer",
        message_suffix="the scorer will score 0 for this rule",
        valid_paths=valid_paths,
    )
    _append_unknown_field_warnings(
        issues,
        rules=bundle.constraints.get("avoid", []),
        path_prefix="constraints.avoid",
        message_suffix="the scorer will score 0 for this rule",
        valid_paths=valid_paths,
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
        valid_paths=valid_paths,
    )


def save_bundle(
    task_id: str,
    profile_id: str,
    bundle: ProfileBundle,
    plugin: TaskPlugin,
    deps: ApplicationDependencies | None = None,
) -> BundleSaveResponse:
    issues: list[ValidationIssue] = []

    bundle.task_id = task_id
    bundle.profile_id = profile_id

    _validate_payload_type(
        model_cls=plugin.constraints_model,
        value=bundle.constraints,
        prefix="constraints",
        issues=issues,
    )

    if not isinstance(bundle.task_config, dict):
        issues.append(
            ValidationIssue(
                path="task_config",
                code="invalid_type",
                message="task_config must be a JSON object",
                severity="error",
            )
        )

    _validate_task_runtime(bundle, plugin, issues)

    if any(i.severity == "error" for i in issues):
        return BundleSaveResponse(valid=False, issues=issues)

    _append_rule_warnings(bundle, plugin, issues)
    _validate_task_field_paths(bundle, plugin, issues)

    resolved = resolve_dependencies(deps)
    resolved.profile_repo.save_bundle(task_id, profile_id, bundle_to_data(bundle))
    return BundleSaveResponse(valid=True, issues=issues)
