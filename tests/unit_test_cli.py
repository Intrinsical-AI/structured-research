"""Unit tests for unified structured-search CLI routing."""

from __future__ import annotations

import json
from pathlib import Path

import structured_search.cli as cli
from structured_search.contracts import RunValidateChecks, RunValidateSummary


def test_parser_accepts_task_run_validate_command():
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "task",
            "job_search",
            "run-validate",
            "--request",
            "request.json",
        ]
    )
    assert args.group == "task"
    assert args.task_id == "job_search"
    assert args.task_cmd == "run-validate"
    assert callable(args.func)


def test_run_validate_returns_2_when_ok_false_and_fail_enabled(tmp_path: Path, monkeypatch):
    request_file = tmp_path / "request.json"
    request_file.write_text(
        json.dumps(
            {
                "profile_id": "profile_example",
                "records": [],
                "require_snapshot": True,
            }
        ),
        encoding="utf-8",
    )

    def _fake_validate_run(*_args, **_kwargs):
        return RunValidateSummary(
            ok=False,
            profile_id="profile_example",
            total_records=0,
            valid_records=0,
            invalid_records=0,
            errors=[],
            checks=RunValidateChecks(
                profile_exists=True,
                constraints_valid=True,
                scoring_config_valid=True,
                all_records_schema_valid=True,
                snapshot_io_checked=True,
                snapshot_io_writable=False,
            ),
            snapshot_probe_dir=None,
            snapshot_probe_error="probe failed",
        )

    monkeypatch.setattr(cli, "validate_run", _fake_validate_run)
    exit_code = cli.main(
        [
            "task",
            "job_search",
            "run-validate",
            "--request",
            str(request_file),
        ]
    )
    assert exit_code == 2


def test_metrics_report_dispatches_to_module(monkeypatch):
    captured: list[list[str] | None] = []

    def _fake_main(argv=None):
        captured.append(argv)
        return 0

    monkeypatch.setattr(cli.report_q2_metrics, "main", _fake_main)
    exit_code = cli.main(["metrics", "report", "--days", "3", "--json"])
    assert exit_code == 0
    assert captured == [["--metrics-log", "runs/metrics_q2_events.jsonl", "--days", "3", "--json"]]


def test_parser_accepts_tasks_list_command():
    parser = cli.build_parser()
    args = parser.parse_args(["tasks", "list"])
    assert args.group == "tasks"
    assert args.tasks_cmd == "list"
    assert callable(args.func)


def test_parser_accepts_task_action_command():
    parser = cli.build_parser()
    args = parser.parse_args(
        ["task", "gen_cv", "action", "--name", "gen-cv", "--request", "req.json"]
    )
    assert args.group == "task"
    assert args.task_id == "gen_cv"
    assert args.task_cmd == "action"
    assert callable(args.func)


def test_tools_export_openapi_dispatches_to_module(monkeypatch):
    captured: list[list[str] | None] = []

    def _fake_main(argv=None):
        captured.append(argv)
        return 0

    monkeypatch.setattr(cli.export_openapi, "main", _fake_main)
    exit_code = cli.main(
        [
            "tools",
            "export-openapi",
            "--output",
            "docs/openapi_v1.json",
        ]
    )
    assert exit_code == 0
    assert captured == [["--output", "docs/openapi_v1.json"]]


def test_tools_export_ui_types_dispatches_to_module(monkeypatch):
    captured: list[list[str] | None] = []

    def _fake_main(argv=None):
        captured.append(argv)
        return 0

    monkeypatch.setattr(cli.export_ui_types, "main", _fake_main)
    exit_code = cli.main(
        [
            "tools",
            "export-ui-types",
            "--openapi",
            "docs/openapi_v1.json",
            "--output",
            "ui/lib/generated/api-types.ts",
        ]
    )
    assert exit_code == 0
    assert captured == [
        ["--openapi", "docs/openapi_v1.json", "--output", "ui/lib/generated/api-types.ts"]
    ]
