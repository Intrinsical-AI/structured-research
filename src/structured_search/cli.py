"""Unified command-line entrypoint for structured-search workflows."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from structured_search.api.wiring import (
    configure_filesystem_dependencies,
    configure_wired_registry,
)
from structured_search.application.core.ingest_service import ingest_validate_jsonl
from structured_search.application.core.prompt_service import generate_prompt
from structured_search.application.core.run_service import run_score, validate_run
from structured_search.application.core.task_registry import get_task_registry
from structured_search.contracts import GenCVRequest, RunScoreRequest
from structured_search.tools import (
    export_openapi,
    export_ui_types,
    extract_p2_postings,
    populate_jsonl_validate_metrics,
    report_q2_metrics,
    scaffold_task,
    validate_atoms,
    validate_results,
)

DEFAULT_API_HOST = "127.0.0.1"
DEFAULT_API_PORT = 8000
DEFAULT_UI_PORT = 3000


class NoAbbrevArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("allow_abbrev", False)
        super().__init__(*args, **kwargs)


def _run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> int:
    completed = subprocess.run(cmd, cwd=cwd, env=env, check=False)
    return int(completed.returncode)


def _require_executable(name: str, install_hint: str) -> int:
    if shutil.which(name):
        return 0
    print(f"Missing executable '{name}'. {install_hint}", file=sys.stderr)
    return 1


def _plugin_or_exit(task_id: str):
    registry = get_task_registry()
    try:
        return registry.get(task_id)
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _cmd_quality_lint(_args: argparse.Namespace) -> int:
    rc = _run(["ruff", "check", "src/", "tests/"])
    if rc != 0:
        return rc
    return _run(["ruff", "format", "--check", "src/", "tests/"])


def _cmd_quality_format(_args: argparse.Namespace) -> int:
    rc = _run(["ruff", "format", "src/", "tests/"])
    if rc != 0:
        return rc
    return _run(["ruff", "check", "--fix", "src/", "tests/"])


def _cmd_quality_test(args: argparse.Namespace) -> int:
    cmd = ["pytest", "tests/", "-v"]
    if args.quick:
        cmd = ["pytest", "-q"]
    return _run(cmd)


def _cmd_quality_arch_lint(_args: argparse.Namespace) -> int:
    return _run(["lint-imports"])


def _cmd_metrics_report(args: argparse.Namespace) -> int:
    argv: list[str] = []
    if args.metrics_log:
        argv += ["--metrics-log", args.metrics_log]
    if args.days is not None:
        argv += ["--days", str(args.days)]
    if args.json:
        argv.append("--json")
    return report_q2_metrics.main(argv)


def _cmd_metrics_populate(args: argparse.Namespace) -> int:
    argv: list[str] = [
        "--api-base",
        args.api_base,
        "--task-id",
        args.task_id,
        "--profile-id",
        args.profile_id,
        "--glob",
        args.glob_pattern,
        "--max-files",
        str(args.max_files),
        "--timeout",
        str(args.timeout),
    ]
    for item in args.inputs:
        argv += ["--input", item]
    return populate_jsonl_validate_metrics.main(argv)


def _cmd_tasks_list(_args: argparse.Namespace) -> int:
    tasks = [item.model_dump(mode="json") for item in get_task_registry().list()]
    print(json.dumps(tasks, indent=2, ensure_ascii=False))
    return 0


def _cmd_task_prompt(args: argparse.Namespace) -> int:
    plugin = _plugin_or_exit(args.task_id)
    if not plugin.supports("prompt"):
        print(f"Task {args.task_id!r} does not support prompt", file=sys.stderr)
        return 1

    step_dir = Path("resources/prompts") / plugin.prompt_namespace / "steps"
    if not step_dir.exists() or not any(step_dir.glob(f"{args.step}*.md")):
        print(
            f"Prompt step file not found for task={args.task_id!r} step={args.step!r} "
            f"in {step_dir}",
            file=sys.stderr,
        )
        return 1

    try:
        result = generate_prompt(
            task_id=args.task_id,
            profile_id=args.profile_id,
            step=args.step,
            plugin=plugin,
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(result.prompt, encoding="utf-8")
        print(f"Prompt written to {out}")
    else:
        print(result.prompt)
    return 0


def _cmd_task_run(args: argparse.Namespace) -> int:
    plugin = _plugin_or_exit(args.task_id)
    if not plugin.supports("run") or plugin.record_model is None:
        print(f"Task {args.task_id!r} does not support run", file=sys.stderr)
        return 1

    input_path = Path(args.input_path)
    if not input_path.is_file():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 1

    raw_text = input_path.read_text(encoding="utf-8")
    ingest = ingest_validate_jsonl(raw_text=raw_text, record_model=plugin.record_model)

    request = RunScoreRequest(
        profile_id=args.profile_id,
        records=ingest.valid,
        require_snapshot=args.require_snapshot,
    )

    try:
        summary = run_score(task_id=args.task_id, request=request, plugin=plugin)
    except Exception as exc:
        print(f"Run failed: {exc}", file=sys.stderr)
        return 1

    output_path = Path(args.output_path)
    _write_jsonl(output_path, summary.records)

    print(f"Loaded lines:      {ingest.stats.total_lines}")
    print(f"Schema valid:      {ingest.stats.schema_ok}")
    print(f"Schema invalid:    {ingest.stats.schema_errors}")
    print(f"Scored records:    {len(summary.records)}")
    print(f"Gate passed:       {summary.gate_passed}")
    print(f"Gate failed:       {summary.gate_failed}")
    print(f"Output:            {output_path}")
    return 0


def _load_run_request_from_input(
    *, plugin, profile_id: str, input_path: Path, require_snapshot: bool
):
    raw_text = input_path.read_text(encoding="utf-8")
    ingest = ingest_validate_jsonl(raw_text=raw_text, record_model=plugin.record_model)
    request = RunScoreRequest(
        profile_id=profile_id,
        records=ingest.valid,
        require_snapshot=require_snapshot,
    )
    return request


def _cmd_task_run_validate(args: argparse.Namespace) -> int:
    plugin = _plugin_or_exit(args.task_id)
    if not plugin.supports("run") or plugin.record_model is None:
        print(f"Task {args.task_id!r} does not support run-validate", file=sys.stderr)
        return 1

    if args.request:
        request_path = Path(args.request)
        if not request_path.is_file():
            print(f"Request file not found: {request_path}", file=sys.stderr)
            return 1
        try:
            payload = json.loads(request_path.read_text(encoding="utf-8"))
            request = RunScoreRequest.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            print(f"Invalid run request file: {exc}", file=sys.stderr)
            return 1
    else:
        if args.input_path is None:
            print("Either --request or --input is required", file=sys.stderr)
            return 1
        input_path = Path(args.input_path)
        if not input_path.is_file():
            print(f"Input file not found: {input_path}", file=sys.stderr)
            return 1
        request = _load_run_request_from_input(
            plugin=plugin,
            profile_id=args.profile_id,
            input_path=input_path,
            require_snapshot=args.require_snapshot,
        )

    try:
        response = validate_run(task_id=args.task_id, request=request, plugin=plugin)
    except Exception as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(response.model_dump(mode="json"), indent=2, ensure_ascii=False))
    if args.fail_on_not_ok and response.ok is False:
        return 2
    return 0


def _cmd_task_action(args: argparse.Namespace) -> int:
    plugin = _plugin_or_exit(args.task_id)
    action_name = args.action_name
    if not plugin.supports(f"action:{action_name}"):
        print(
            f"Task {args.task_id!r} does not support action {action_name!r}",
            file=sys.stderr,
        )
        return 1

    handler = plugin.action_handlers.get(action_name)
    if handler is None:
        print(f"Action handler not found for {action_name!r}", file=sys.stderr)
        return 1

    request_path = Path(args.request)
    if not request_path.is_file():
        print(f"Request file not found: {request_path}", file=sys.stderr)
        return 1

    try:
        payload = json.loads(request_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON in request file: {exc}", file=sys.stderr)
        return 1

    try:
        if action_name == "gen-cv":
            request = GenCVRequest.model_validate(payload)
            response = handler(
                profile_id=request.profile_id,
                job=request.job,
                candidate_profile=request.candidate_profile,
                selected_claim_ids=request.selected_claim_ids,
                llm_model=request.llm_model,
                allow_mock_fallback=request.allow_mock_fallback,
            )
        else:
            response = handler(**payload)
    except Exception as exc:
        print(f"Action failed: {exc}", file=sys.stderr)
        return 1

    if hasattr(response, "model_dump"):
        print(json.dumps(response.model_dump(mode="json"), indent=2, ensure_ascii=False))
    else:
        print(json.dumps(response, indent=2, ensure_ascii=False))
    return 0


def _cmd_api_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError as exc:
        print(f"Missing dependency for API server: {exc}", file=sys.stderr)
        return 1
    uvicorn.run(
        "structured_search.api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


def _cmd_dev_api_install(args: argparse.Namespace) -> int:
    if _require_executable("uv", "Install uv and retry.") != 0:
        return 1
    env = os.environ.copy()
    if args.uv_cache_dir:
        env["UV_CACHE_DIR"] = args.uv_cache_dir
    return _run(["uv", "sync", "--extra", "api", "--extra", "ollama"], env=env)


def _cmd_dev_ui_install(args: argparse.Namespace) -> int:
    if _require_executable("npm", "Install Node.js/npm and retry.") != 0:
        return 1
    return _run(["npm", "install"], cwd=Path(args.ui_dir))


def _api_command(host: str, port: int, reload_enabled: bool) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "structured_search.api.app:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if reload_enabled:
        cmd.append("--reload")
    return cmd


def _cmd_dev_api(args: argparse.Namespace) -> int:
    return _run(_api_command(args.host, args.port, args.reload))


def _cmd_dev_ui(args: argparse.Namespace) -> int:
    if _require_executable("npm", "Install Node.js/npm and retry.") != 0:
        return 1
    env = os.environ.copy()
    env["NEXT_PUBLIC_API_BASE"] = args.api_base
    return _run(
        ["npm", "run", "dev", "--", "--port", str(args.ui_port)],
        cwd=Path(args.ui_dir),
        env=env,
    )


def _cmd_dev_all(args: argparse.Namespace) -> int:
    if _require_executable("npm", "Install Node.js/npm and retry.") != 0:
        return 1

    api_base = args.api_base or f"http://{args.host}:{args.port}/v1"
    api_cmd = _api_command(args.host, args.port, args.reload)
    api_proc = subprocess.Popen(api_cmd)

    env = os.environ.copy()
    env["NEXT_PUBLIC_API_BASE"] = api_base
    try:
        ui_rc = _run(
            ["npm", "run", "dev", "--", "--port", str(args.ui_port)],
            cwd=Path(args.ui_dir),
            env=env,
        )
    finally:
        if api_proc.poll() is None:
            api_proc.terminate()
            try:
                api_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                api_proc.kill()
                api_proc.wait(timeout=10)
    return ui_rc


def _remove_paths(paths: list[Path]) -> None:
    for path in paths:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.is_file():
            path.unlink(missing_ok=True)


def _cmd_clean(_args: argparse.Namespace) -> int:
    root = Path(".")
    for pycache_dir in root.rglob("__pycache__"):
        if pycache_dir.is_dir():
            shutil.rmtree(pycache_dir, ignore_errors=True)
    for file_path in root.rglob("*.pyc"):
        file_path.unlink(missing_ok=True)
    for file_path in root.rglob("*.pyo"):
        file_path.unlink(missing_ok=True)
    for egg_info in root.rglob("*.egg-info"):
        if egg_info.is_dir():
            shutil.rmtree(egg_info, ignore_errors=True)
    _remove_paths(
        [
            Path(".pytest_cache"),
            Path(".mypy_cache"),
            Path(".next"),
            Path("out"),
            Path("coverage"),
            Path(".swc"),
            Path(".eslintcache"),
        ]
    )
    return 0


def _cmd_tools_validate_results(args: argparse.Namespace) -> int:
    argv = [
        "--input-dir",
        args.input_dir,
        "--output-dir",
        args.output_dir,
        "--task-id",
        args.task_id,
    ]
    if args.strict:
        argv.append("--strict")
    return validate_results.main(argv)


def _cmd_tools_validate_atoms(args: argparse.Namespace) -> int:
    return validate_atoms.main(
        [
            "--atoms-dir",
            args.atoms_dir,
            "--schemas-dir",
            args.schemas_dir,
            "--canon-tags",
            args.canon_tags,
        ]
    )


def _cmd_tools_scaffold_task(args: argparse.Namespace) -> int:
    return scaffold_task.main(["--task-id", args.task_id])


def _cmd_tools_extract_p2(args: argparse.Namespace) -> int:
    return extract_p2_postings.main(["--input", args.input_path, "--output-dir", args.output_dir])


def _cmd_tools_export_openapi(args: argparse.Namespace) -> int:
    return export_openapi.main(["--output", args.output])


def _cmd_tools_export_ui_types(args: argparse.Namespace) -> int:
    return export_ui_types.main(["--openapi", args.openapi, "--output", args.output])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="structured-search", allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="group", parser_class=NoAbbrevArgumentParser)

    quality = subparsers.add_parser("quality", help="Lint, format, test and architecture checks")
    quality_sub = quality.add_subparsers(
        dest="quality_cmd",
        parser_class=NoAbbrevArgumentParser,
    )
    quality_lint = quality_sub.add_parser("lint", help="ruff check + format check")
    quality_lint.set_defaults(func=_cmd_quality_lint)
    quality_format = quality_sub.add_parser("format", help="ruff format + ruff --fix")
    quality_format.set_defaults(func=_cmd_quality_format)
    quality_test = quality_sub.add_parser("test", help="pytest suite")
    quality_test.add_argument("--quick", action="store_true", help="Use pytest -q")
    quality_test.set_defaults(func=_cmd_quality_test)
    quality_arch = quality_sub.add_parser("arch-lint", help="import-linter contracts")
    quality_arch.set_defaults(func=_cmd_quality_arch_lint)

    metrics = subparsers.add_parser("metrics", help="Q2 metrics reporting and population")
    metrics_sub = metrics.add_subparsers(
        dest="metrics_cmd",
        parser_class=NoAbbrevArgumentParser,
    )
    metrics_report = metrics_sub.add_parser("report", help="Compute Q2 report from metric events")
    metrics_report.add_argument("--metrics-log", default="runs/metrics_q2_events.jsonl")
    metrics_report.add_argument("--days", type=int, default=7)
    metrics_report.add_argument("--json", action="store_true")
    metrics_report.set_defaults(func=_cmd_metrics_report)

    metrics_populate = metrics_sub.add_parser(
        "populate", help="Call task JSONL validation endpoint"
    )
    metrics_populate.add_argument(
        "--api-base", default=f"http://{DEFAULT_API_HOST}:{DEFAULT_API_PORT}/v1"
    )
    metrics_populate.add_argument("--task-id", default="job_search")
    metrics_populate.add_argument("--profile-id", default="profile_example")
    metrics_populate.add_argument("--input", dest="inputs", action="append", default=[])
    metrics_populate.add_argument(
        "--glob", dest="glob_pattern", default="results/job_search/**/results.jsonl"
    )
    metrics_populate.add_argument("--max-files", type=int, default=0)
    metrics_populate.add_argument("--timeout", type=float, default=30.0)
    metrics_populate.set_defaults(func=_cmd_metrics_populate)

    tasks_parser = subparsers.add_parser("tasks", help="Task registry operations")
    tasks_sub = tasks_parser.add_subparsers(
        dest="tasks_cmd",
        parser_class=NoAbbrevArgumentParser,
    )
    tasks_list = tasks_sub.add_parser("list", help="List registered tasks")
    tasks_list.set_defaults(func=_cmd_tasks_list)

    task = subparsers.add_parser("task", help="Execute one task workflow")
    task.add_argument("task_id", help="Task identifier (e.g., job_search, product_search, gen_cv)")
    task_sub = task.add_subparsers(
        dest="task_cmd",
        parser_class=NoAbbrevArgumentParser,
    )

    task_prompt = task_sub.add_parser("prompt", help="Compose extraction prompt")
    task_prompt.add_argument(
        "--profile-id",
        required=True,
        help="Profile identifier (e.g., profile_example)",
    )
    task_prompt.add_argument("--step", default="S3_execute")
    task_prompt.add_argument("--output", default=None)
    task_prompt.set_defaults(func=_cmd_task_prompt)

    task_run = task_sub.add_parser("run", help="Run deterministic scoring on JSONL input")
    task_run.add_argument(
        "--profile-id",
        required=True,
        help="Profile identifier (e.g., profile_example)",
    )
    task_run.add_argument("--input", dest="input_path", required=True)
    task_run.add_argument("--output", dest="output_path", required=True)
    task_run.add_argument("--require-snapshot", action="store_true")
    task_run.set_defaults(func=_cmd_task_run)

    task_validate = task_sub.add_parser("run-validate", help="Dry-run validate run prerequisites")
    task_validate.add_argument(
        "--request", default=None, help="JSON file with RunScoreRequest payload"
    )
    task_validate.add_argument(
        "--profile-id",
        default="profile_example",
        help="Profile identifier used when --request is omitted",
    )
    task_validate.add_argument(
        "--input", dest="input_path", default=None, help="Used when --request is omitted"
    )
    task_validate.add_argument("--require-snapshot", action="store_true")
    task_validate.add_argument(
        "--allow-not-ok",
        action="store_false",
        dest="fail_on_not_ok",
        help="Return 0 even if response.ok is false",
    )
    task_validate.set_defaults(func=_cmd_task_run_validate, fail_on_not_ok=True)

    task_action = task_sub.add_parser("action", help="Execute a task action handler")
    task_action.add_argument(
        "--action-name",
        required=True,
        help="Action name (e.g., gen-cv)",
    )
    task_action.add_argument("--request", required=True, help="JSON request payload file")
    task_action.set_defaults(func=_cmd_task_action)

    api = subparsers.add_parser("api", help="HTTP API operations")
    api_sub = api.add_subparsers(dest="api_cmd", parser_class=NoAbbrevArgumentParser)
    api_serve = api_sub.add_parser("serve", help="Run FastAPI server with uvicorn")
    api_serve.add_argument("--host", default=DEFAULT_API_HOST)
    api_serve.add_argument("--port", type=int, default=DEFAULT_API_PORT)
    api_serve.add_argument("--reload", action="store_true")
    api_serve.set_defaults(func=_cmd_api_serve)

    dev = subparsers.add_parser("dev", help="Local developer workflows")
    dev_sub = dev.add_subparsers(dest="dev_cmd", parser_class=NoAbbrevArgumentParser)
    dev_api_install = dev_sub.add_parser("api-install", help="Install API extras with uv")
    dev_api_install.add_argument("--uv-cache-dir", default="/tmp/uv_cache")
    dev_api_install.set_defaults(func=_cmd_dev_api_install)

    dev_ui_install = dev_sub.add_parser("ui-install", help="Install UI dependencies with npm")
    dev_ui_install.add_argument("--ui-dir", default="ui")
    dev_ui_install.set_defaults(func=_cmd_dev_ui_install)

    dev_api = dev_sub.add_parser("api", help="Run API server")
    dev_api.add_argument("--host", default=DEFAULT_API_HOST)
    dev_api.add_argument("--port", type=int, default=DEFAULT_API_PORT)
    dev_api.add_argument("--reload", action="store_true")
    dev_api.set_defaults(func=_cmd_dev_api)

    dev_ui = dev_sub.add_parser("ui", help="Run UI dev server")
    dev_ui.add_argument("--ui-dir", default="ui")
    dev_ui.add_argument("--api-base", default=f"http://{DEFAULT_API_HOST}:{DEFAULT_API_PORT}/v1")
    dev_ui.add_argument("--ui-port", type=int, default=DEFAULT_UI_PORT)
    dev_ui.set_defaults(func=_cmd_dev_ui)

    dev_all = dev_sub.add_parser("all", help="Run API + UI together")
    dev_all.add_argument("--host", default=DEFAULT_API_HOST)
    dev_all.add_argument("--port", type=int, default=DEFAULT_API_PORT)
    dev_all.add_argument("--reload", action="store_true")
    dev_all.add_argument("--ui-dir", default="ui")
    dev_all.add_argument("--ui-port", type=int, default=DEFAULT_UI_PORT)
    dev_all.add_argument("--api-base", default=None)
    dev_all.set_defaults(func=_cmd_dev_all)

    clean = subparsers.add_parser("clean", help="Remove Python/Node cache artifacts")
    clean.set_defaults(func=_cmd_clean)

    tools = subparsers.add_parser("tools", help="Utility workflows")
    tools_sub = tools.add_subparsers(dest="tools_cmd", parser_class=NoAbbrevArgumentParser)
    tools_validate_results = tools_sub.add_parser("validate-results")
    tools_validate_results.add_argument("--input-dir", required=True)
    tools_validate_results.add_argument("--output-dir", required=True)
    tools_validate_results.add_argument(
        "--task-id",
        default="job_search",
        help="Task identifier (job_search, product_search, gen_cv)",
    )
    tools_validate_results.add_argument("--strict", action="store_true")
    tools_validate_results.set_defaults(func=_cmd_tools_validate_results)

    tools_validate_atoms = tools_sub.add_parser("validate-atoms")
    tools_validate_atoms.add_argument(
        "--atoms-dir", default="config/job_search/profile_example/atoms"
    )
    tools_validate_atoms.add_argument(
        "--schemas-dir", default="config/job_search/profile_example/atoms/schemas"
    )
    tools_validate_atoms.add_argument(
        "--canon-tags", default="config/job_search/profile_example/atoms/canon_tags.yaml"
    )
    tools_validate_atoms.set_defaults(func=_cmd_tools_validate_atoms)

    tools_scaffold_task = tools_sub.add_parser("scaffold-task")
    tools_scaffold_task.add_argument(
        "--task-id", required=True, help="Task identifier to scaffold"
    )
    tools_scaffold_task.set_defaults(func=_cmd_tools_scaffold_task)

    tools_extract_p2 = tools_sub.add_parser("extract-p2-postings")
    tools_extract_p2.add_argument(
        "--input", dest="input_path", default="results/job_search/profile_example/result.jsonl"
    )
    tools_extract_p2.add_argument(
        "--output-dir", default="results/job_search/profile_example/postings"
    )
    tools_extract_p2.set_defaults(func=_cmd_tools_extract_p2)

    tools_export_openapi = tools_sub.add_parser(
        "export-openapi", help="Export FastAPI OpenAPI contract JSON"
    )
    tools_export_openapi.add_argument("--output", default="docs/openapi_v1.json")
    tools_export_openapi.set_defaults(func=_cmd_tools_export_openapi)

    tools_export_ui_types = tools_sub.add_parser(
        "export-ui-types", help="Export TypeScript UI API types from OpenAPI JSON"
    )
    tools_export_ui_types.add_argument("--openapi", default="docs/openapi_v1.json")
    tools_export_ui_types.add_argument("--output", default="ui/lib/generated/api-types.ts")
    tools_export_ui_types.set_defaults(func=_cmd_tools_export_ui_types)

    return parser


def main(argv: list[str] | None = None) -> int:
    configure_filesystem_dependencies()
    configure_wired_registry()
    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 1
    try:
        return int(func(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
