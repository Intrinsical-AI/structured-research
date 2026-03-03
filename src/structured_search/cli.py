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
from urllib import error as urllib_error
from urllib import request as urllib_request

from structured_search.tasks.gen_cv import cli as gen_cv_cli
from structured_search.tasks.job_search import cli as job_search_cli
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
DEFAULT_API_BASE = f"http://{DEFAULT_API_HOST}:{DEFAULT_API_PORT}/v1"


def _run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> int:
    completed = subprocess.run(cmd, cwd=cwd, env=env, check=False)
    return int(completed.returncode)


def _require_executable(name: str, install_hint: str) -> int:
    if shutil.which(name):
        return 0
    print(f"Missing executable '{name}'. {install_hint}", file=sys.stderr)
    return 1


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


def _cmd_job_search_prompt(args: argparse.Namespace) -> int:
    argv: list[str] = ["prompt", "--step", args.step]
    if args.profile:
        argv += ["--profile", args.profile]
    if args.output:
        argv += ["--output", args.output]
    if args.prompts_dir:
        argv += ["--prompts-dir", args.prompts_dir]
    if args.constraints:
        argv += ["--constraints", args.constraints]
    if args.verbose:
        argv.append("--verbose")
    return job_search_cli.main(argv)


def _cmd_job_search_run(args: argparse.Namespace) -> int:
    argv: list[str] = ["run", "--input", args.input_path, "--output", args.output_path]
    if args.profile:
        argv += ["--profile", args.profile]
    if args.constraints:
        argv += ["--constraints", args.constraints]
    if args.verbose:
        argv.append("--verbose")
    return job_search_cli.main(argv)


def _normalize_api_base(api_base: str) -> str:
    base = api_base.rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    return base


def _call_json_endpoint(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    req = urllib_request.Request(
        url,
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib_request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} on {url}: {detail}") from exc
    except urllib_error.URLError as exc:
        raise RuntimeError(f"Cannot reach {url}: {exc}") from exc
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON response from {url}: {body[:200]}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected response type from {url}: {type(payload).__name__}")
    return payload


def _cmd_job_search_run_validate(args: argparse.Namespace) -> int:
    request_path = Path(args.request)
    if not request_path.is_file():
        print(f"Request file not found: {request_path}", file=sys.stderr)
        return 1
    try:
        request_payload = json.loads(request_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON in request file {request_path}: {exc}", file=sys.stderr)
        return 1
    if not isinstance(request_payload, dict):
        print(f"Request payload must be an object: {request_path}", file=sys.stderr)
        return 1

    url = f"{_normalize_api_base(args.api_base)}/job-search/run/validate"
    try:
        response = _call_json_endpoint(url, request_payload, args.timeout)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(response, indent=2, ensure_ascii=False))
    if args.fail_on_not_ok and response.get("ok") is False:
        return 2
    return 0


def _cmd_gen_cv_run(args: argparse.Namespace) -> int:
    argv: list[str] = ["run", "--job", args.job, "--candidate", args.candidate]
    if args.profile:
        argv += ["--profile", args.profile]
    if args.atoms_dir:
        argv += ["--atoms-dir", args.atoms_dir]
    if args.llm_model:
        argv += ["--llm-model", args.llm_model]
    if args.prompts_dir:
        argv += ["--prompts-dir", args.prompts_dir]
    if args.output:
        argv += ["--output", args.output]
    if args.verbose:
        argv.append("--verbose")
    return gen_cv_cli.main(argv)


def _cmd_gen_cv_prompt(args: argparse.Namespace) -> int:
    argv: list[str] = ["prompt", "--job", args.job, "--candidate", args.candidate]
    if args.profile:
        argv += ["--profile", args.profile]
    if args.atoms_dir:
        argv += ["--atoms-dir", args.atoms_dir]
    if args.prompts_dir:
        argv += ["--prompts-dir", args.prompts_dir]
    for claim_id in args.allowed_claim_ids:
        argv += ["--allowed-claim-id", claim_id]
    if args.output:
        argv += ["--output", args.output]
    if args.base_output:
        argv += ["--base-output", args.base_output]
    if args.verbose:
        argv.append("--verbose")
    return gen_cv_cli.main(argv)


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
    argv = ["--input-dir", args.input_dir, "--output-dir", args.output_dir, "--task", args.task]
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
    return scaffold_task.main(["--name", args.name])


def _cmd_tools_extract_p2(args: argparse.Namespace) -> int:
    return extract_p2_postings.main(["--input", args.input_path, "--output-dir", args.output_dir])


def _cmd_tools_export_openapi(args: argparse.Namespace) -> int:
    return export_openapi.main(["--output", args.output])


def _cmd_tools_export_ui_types(args: argparse.Namespace) -> int:
    return export_ui_types.main(["--openapi", args.openapi, "--output", args.output])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="structured-search")
    subparsers = parser.add_subparsers(dest="group")

    quality = subparsers.add_parser("quality", help="Lint, format, test and architecture checks")
    quality_sub = quality.add_subparsers(dest="quality_cmd")
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
    metrics_sub = metrics.add_subparsers(dest="metrics_cmd")
    metrics_report = metrics_sub.add_parser("report", help="Compute Q2 report from metric events")
    metrics_report.add_argument("--metrics-log", default="runs/metrics_q2_events.jsonl")
    metrics_report.add_argument("--days", type=int, default=7)
    metrics_report.add_argument("--json", action="store_true")
    metrics_report.set_defaults(func=_cmd_metrics_report)
    metrics_populate = metrics_sub.add_parser(
        "populate", help="Call /job-search/jsonl/validate over result files"
    )
    metrics_populate.add_argument("--api-base", default=DEFAULT_API_BASE)
    metrics_populate.add_argument("--profile-id", default="profile_1")
    metrics_populate.add_argument("--input", dest="inputs", action="append", default=[])
    metrics_populate.add_argument(
        "--glob", dest="glob_pattern", default="results/job_search/**/results.jsonl"
    )
    metrics_populate.add_argument("--max-files", type=int, default=0)
    metrics_populate.add_argument("--timeout", type=float, default=30.0)
    metrics_populate.set_defaults(func=_cmd_metrics_populate)

    job = subparsers.add_parser("job-search", help="Job-search prompt/run workflows")
    job_sub = job.add_subparsers(dest="job_cmd")
    job_prompt = job_sub.add_parser("prompt", help="Compose extraction prompt")
    job_prompt.add_argument("--profile", default=None)
    job_prompt.add_argument("--step", default="S3_execute")
    job_prompt.add_argument("--output", default=None)
    job_prompt.add_argument("--prompts-dir", default=None)
    job_prompt.add_argument("--constraints", default=None)
    job_prompt.add_argument("--verbose", action="store_true")
    job_prompt.set_defaults(func=_cmd_job_search_prompt)

    job_run = job_sub.add_parser("run", help="Run ETL scoring pipeline over JSONL")
    job_run.add_argument("--profile", default=None)
    job_run.add_argument("--input", dest="input_path", required=True)
    job_run.add_argument("--output", dest="output_path", required=True)
    job_run.add_argument("--constraints", default=None)
    job_run.add_argument("--verbose", action="store_true")
    job_run.set_defaults(func=_cmd_job_search_run)

    job_validate = job_sub.add_parser("run-validate", help="Dry-run preflight against /run")
    job_validate.add_argument("--request", required=True, help="JSON file with /run payload")
    job_validate.add_argument("--api-base", default=DEFAULT_API_BASE)
    job_validate.add_argument("--timeout", type=float, default=30.0)
    job_validate.add_argument(
        "--allow-not-ok",
        action="store_false",
        dest="fail_on_not_ok",
        help="Return 0 even if response.ok is false",
    )
    job_validate.set_defaults(func=_cmd_job_search_run_validate, fail_on_not_ok=True)

    gen_cv = subparsers.add_parser("gen-cv", help="CV generation workflows")
    gen_cv_sub = gen_cv.add_subparsers(dest="gen_cv_cmd")
    gen_cv_prompt = gen_cv_sub.add_parser(
        "prompt",
        help="Render GEN_CV prompt with atoms embedded and export Markdown files",
    )
    gen_cv_prompt.add_argument("--job", required=True)
    gen_cv_prompt.add_argument("--candidate", required=True)
    gen_cv_prompt.add_argument("--profile", default=None)
    gen_cv_prompt.add_argument("--atoms-dir", default=None)
    gen_cv_prompt.add_argument("--prompts-dir", default="resources/prompts")
    gen_cv_prompt.add_argument(
        "--allowed-claim-id",
        action="append",
        dest="allowed_claim_ids",
        default=[],
        help="Restrict grounded claims to specific IDs (repeatable)",
    )
    gen_cv_prompt.add_argument("--output", default="gen_cv_prompt.md")
    gen_cv_prompt.add_argument("--base-output", default=None)
    gen_cv_prompt.add_argument("--verbose", action="store_true")
    gen_cv_prompt.set_defaults(func=_cmd_gen_cv_prompt)

    gen_cv_run = gen_cv_sub.add_parser("run", help="Generate CV JSON")
    gen_cv_run.add_argument("--job", required=True)
    gen_cv_run.add_argument("--candidate", required=True)
    gen_cv_run.add_argument("--profile", default=None)
    gen_cv_run.add_argument("--atoms-dir", default=None)
    gen_cv_run.add_argument("--llm-model", default="lfm2.5-thinking")
    gen_cv_run.add_argument("--prompts-dir", default=None)
    gen_cv_run.add_argument("--output", default="cv.json")
    gen_cv_run.add_argument("--verbose", action="store_true")
    gen_cv_run.set_defaults(func=_cmd_gen_cv_run)

    api = subparsers.add_parser("api", help="HTTP API operations")
    api_sub = api.add_subparsers(dest="api_cmd")
    api_serve = api_sub.add_parser("serve", help="Run FastAPI server with uvicorn")
    api_serve.add_argument("--host", default=DEFAULT_API_HOST)
    api_serve.add_argument("--port", type=int, default=DEFAULT_API_PORT)
    api_serve.add_argument("--reload", action="store_true")
    api_serve.set_defaults(func=_cmd_api_serve)

    dev = subparsers.add_parser("dev", help="Local developer workflows")
    dev_sub = dev.add_subparsers(dest="dev_cmd")
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
    dev_ui.add_argument("--api-base", default=DEFAULT_API_BASE)
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
    tools_sub = tools.add_subparsers(dest="tools_cmd")
    tools_validate_results = tools_sub.add_parser("validate-results")
    tools_validate_results.add_argument("--input-dir", required=True)
    tools_validate_results.add_argument("--output-dir", required=True)
    tools_validate_results.add_argument("--task", default="job_search")
    tools_validate_results.add_argument("--strict", action="store_true")
    tools_validate_results.set_defaults(func=_cmd_tools_validate_results)

    tools_validate_atoms = tools_sub.add_parser("validate-atoms")
    tools_validate_atoms.add_argument("--atoms-dir", default="config/job_search/profile_1/atoms")
    tools_validate_atoms.add_argument(
        "--schemas-dir", default="config/job_search/profile_1/atoms/schemas"
    )
    tools_validate_atoms.add_argument(
        "--canon-tags", default="config/job_search/profile_1/atoms/canon_tags.yaml"
    )
    tools_validate_atoms.set_defaults(func=_cmd_tools_validate_atoms)

    tools_scaffold_task = tools_sub.add_parser("scaffold-task")
    tools_scaffold_task.add_argument("--name", required=True)
    tools_scaffold_task.set_defaults(func=_cmd_tools_scaffold_task)

    tools_extract_p2 = tools_sub.add_parser("extract-p2-postings")
    tools_extract_p2.add_argument(
        "--input",
        dest="input_path",
        default="results/job_search/profile_1/result.jsonl",
    )
    tools_extract_p2.add_argument(
        "--output-dir",
        default="results/job_search/profile_1/postings",
    )
    tools_extract_p2.set_defaults(func=_cmd_tools_extract_p2)

    tools_export_openapi = tools_sub.add_parser(
        "export-openapi",
        help="Export FastAPI OpenAPI contract JSON",
    )
    tools_export_openapi.add_argument("--output", default="docs/openapi_v1.json")
    tools_export_openapi.set_defaults(func=_cmd_tools_export_openapi)

    tools_export_ui_types = tools_sub.add_parser(
        "export-ui-types",
        help="Export TypeScript UI API types from OpenAPI JSON",
    )
    tools_export_ui_types.add_argument("--openapi", default="docs/openapi_v1.json")
    tools_export_ui_types.add_argument("--output", default="ui/lib/generated/api-types.ts")
    tools_export_ui_types.set_defaults(func=_cmd_tools_export_ui_types)

    return parser


def main(argv: list[str] | None = None) -> int:
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
