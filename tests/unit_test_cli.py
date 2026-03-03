"""Unit tests for unified structured-search CLI routing."""

from __future__ import annotations

import json
from pathlib import Path

import structured_search.cli as cli


def test_parser_accepts_job_search_run_validate_command():
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "job-search",
            "run-validate",
            "--request",
            "request.json",
            "--api-base",
            "http://127.0.0.1:8000/v1",
        ]
    )
    assert args.group == "job-search"
    assert args.job_cmd == "run-validate"
    assert callable(args.func)


def test_run_validate_returns_2_when_ok_false_and_fail_enabled(tmp_path: Path, monkeypatch):
    request_file = tmp_path / "request.json"
    request_file.write_text(
        json.dumps(
            {
                "profile_id": "profile_1",
                "records": [],
                "require_snapshot": True,
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "_call_json_endpoint", lambda *_a, **_k: {"ok": False})
    exit_code = cli.main(
        [
            "job-search",
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


def test_parser_accepts_gen_cv_prompt_command():
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "gen-cv",
            "prompt",
            "--job",
            "job.json",
            "--candidate",
            "candidate.json",
        ]
    )
    assert args.group == "gen-cv"
    assert args.gen_cv_cmd == "prompt"
    assert callable(args.func)


def test_gen_cv_prompt_dispatches_to_task_cli(monkeypatch):
    captured: list[list[str] | None] = []

    def _fake_main(argv=None):
        captured.append(argv)
        return 0

    monkeypatch.setattr(cli.gen_cv_cli, "main", _fake_main)
    exit_code = cli.main(
        [
            "gen-cv",
            "prompt",
            "--job",
            "job.json",
            "--candidate",
            "candidate.json",
            "--profile",
            "profile_1",
            "--atoms-dir",
            "config/job_search/profile_1/atoms",
            "--prompts-dir",
            "resources/prompts",
            "--allowed-claim-id",
            "claim-1",
            "--output",
            "out/prompt.md",
            "--base-output",
            "out/base.md",
        ]
    )
    assert exit_code == 0
    assert captured == [
        [
            "prompt",
            "--job",
            "job.json",
            "--candidate",
            "candidate.json",
            "--profile",
            "profile_1",
            "--atoms-dir",
            "config/job_search/profile_1/atoms",
            "--prompts-dir",
            "resources/prompts",
            "--allowed-claim-id",
            "claim-1",
            "--output",
            "out/prompt.md",
            "--base-output",
            "out/base.md",
        ]
    ]


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
