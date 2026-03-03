#!/usr/bin/env python3
"""CLI: Job search — phase 1 (generate prompt) or phase 2 (run ETL pipeline).

Workflow:
  Phase 1 — Generate an extraction prompt and paste it into a web UI:
    structured-search job-search prompt [--step S3_execute] [--output prompt.md]

  Phase 2 — Process the JSONL output from the web UI:
    structured-search job-search run --input raw.jsonl --output scored.jsonl
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from pydantic import ValidationError

from structured_search.infra.config_loader import task_json_to_scoring_config
from structured_search.infra.exporting import JSONLExporter
from structured_search.infra.loading import JSONLLoader
from structured_search.infra.prompts import PromptComposer
from structured_search.infra.scoring import HeuristicScorer
from structured_search.infra.scoring_config import SoftScoringConfig
from structured_search.tasks.job_search.models import JobSearchConstraints
from structured_search.tasks.job_search.sanitize import sanitize_jsonl_for_run
from structured_search.tasks.job_search.service import ETLJobSearch

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_DEFAULT_PROFILE = "profile_1"
_PROFILES_BASE = "config/job_search"
_DEFAULT_PROMPTS_DIR = "resources/prompts"


def _profile_bundle_path(profile: str) -> Path:
    return Path(_PROFILES_BASE) / profile / "bundle.json"


def _load_profile_bundle(profile: str) -> dict:
    bundle_path = _profile_bundle_path(profile)
    with open(bundle_path, encoding="utf-8") as f:
        return json.load(f)


def cmd_prompt(args) -> int:
    """Phase 1: compose and print the web UI extraction prompt."""

    prompts_dir = Path(args.prompts_dir or _DEFAULT_PROMPTS_DIR)
    if not prompts_dir.is_dir():
        logger.error(f"Prompts directory not found: {prompts_dir}")
        return 1

    profile = args.profile or _DEFAULT_PROFILE
    composer = PromptComposer(prompts_dir)
    try:
        prompt = composer.compose(task="job_search", step=args.step, profile=profile)
    except Exception as e:
        logger.error(f"Failed to compose prompt: {e}")
        return 1

    # Embed constraints so the prompt is self-contained for copy-paste
    try:
        if args.constraints:
            with open(args.constraints, encoding="utf-8") as f:
                constraints_payload = json.load(f)
        else:
            constraints_payload = _load_profile_bundle(profile)["constraints"]
        constraints_json = json.dumps(constraints_payload, indent=2)
        sep = "\n\n" + "─" * 80 + "\n\n"
        prompt += f"{sep}## Search Constraints\n\n```json\n{constraints_json}\n```"
    except Exception as e:
        logger.warning(f"Could not embed constraints: {e}")

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(prompt, encoding="utf-8")
        print(f"\n Prompt written to {out}")
        print("  → Paste it into Claude.ai, ChatGPT, or Gemini")
        print("  → Save the JSONL response to a local file")
        print(
            "  → Then run: structured-search job-search run"
            " --input <file>.jsonl --output scored.jsonl"
        )
    else:
        print(prompt)

    return 0


def cmd_run(args) -> int:
    """Phase 2: validate, score, and export the JSONL from the web UI."""
    summary = None
    sanitized_input = Path(args.input)

    profile = args.profile or _DEFAULT_PROFILE
    try:
        if args.constraints:
            with open(args.constraints, encoding="utf-8") as f:
                constraints_payload = json.load(f)
        else:
            constraints_payload = _load_profile_bundle(profile)["constraints"]
        constraints = JobSearchConstraints.model_validate(constraints_payload)
    except FileNotFoundError:
        target = args.constraints if args.constraints else _profile_bundle_path(profile)
        logger.error(f"Constraints source not found: {target}")
        return 1
    except (json.JSONDecodeError, ValidationError) as e:
        target = args.constraints if args.constraints else _profile_bundle_path(profile)
        logger.error(f"Invalid constraints source '{target}': {e}")
        return 1

    # Load scoring config from task.json when available; fall back to defaults
    scoring_config = SoftScoringConfig()
    try:
        task_payload = _load_profile_bundle(profile)["task"]
        scoring_config = task_json_to_scoring_config(task_payload)
        logger.info(f"Loaded scoring config from {_profile_bundle_path(profile)}")
    except FileNotFoundError:
        logger.warning(
            f"Could not load profile bundle from {_profile_bundle_path(profile)}: using defaults"
        )
    except Exception as e:
        logger.warning(f"Could not load task config from profile bundle: {e}, using defaults")

    try:
        summary = sanitize_jsonl_for_run(args.input)
        sanitized_input = summary.output_path
    except FileNotFoundError as e:
        logger.error(f"Input file not found: {e}")
        return 1

    if summary.fixed_fields > 0:
        logger.info(
            "Input sanitization applied: touched_records=%s fixed_fields=%s temp_file=%s",
            summary.touched_records,
            summary.fixed_fields,
            sanitized_input,
        )
    if summary.parse_errors > 0:
        logger.warning(
            "Input contains %s unparseable lines; they were left untouched by sanitization",
            summary.parse_errors,
        )

    try:
        result = ETLJobSearch(
            loader=JSONLLoader(),
            scorer=HeuristicScorer(config=scoring_config),
            exporter=JSONLExporter(),
            constraints=constraints,
        ).run(sanitized_input, args.output)
    except FileNotFoundError as e:
        logger.error(f"Input file not found: {e}")
        return 1
    except Exception as e:
        logger.error(f"ETL pipeline failed: {e}")
        return 1
    finally:
        if summary and summary.used_temp_file:
            try:
                sanitized_input.unlink(missing_ok=True)
            except Exception as e:
                logger.warning(
                    f"Could not remove temporary sanitized file '{sanitized_input}': {e}"
                )

    print("\n ETL complete!")
    print(f"  Loaded:    {result['loaded']} records")
    print(f"  Processed: {result['processed']} job postings")
    print(f"  Skipped:   {result['skipped']} (validation errors)")
    print(f"  Output:    {result['output']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Job Search: generate extraction prompt (phase 1) or run ETL pipeline (phase 2)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Workflow:
  Phase 1 — generate prompt, paste into web UI, save JSONL output:
    %(prog)s prompt [--step S3_execute] [--output prompts/job_search.md]

  Phase 2 — validate, score and export the JSONL from the web UI:
    %(prog)s run --input raw.jsonl --output scored.jsonl
""",
    )
    parser.add_argument("--verbose", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # prompt subcommand
    p_prompt = subparsers.add_parser(
        "prompt", help="Compose the web UI extraction prompt (phase 1)"
    )
    p_prompt.add_argument(
        "--profile",
        default=None,
        help=f"Profile name under {_PROFILES_BASE}/ (default: {_DEFAULT_PROFILE})",
    )
    p_prompt.add_argument(
        "--step",
        default="S3_execute",
        help="Prompt step to load (default: S3_execute)",
    )
    p_prompt.add_argument(
        "--output",
        help="Write prompt to file instead of stdout",
    )
    p_prompt.add_argument(
        "--prompts-dir",
        default=None,
        help=f"Path to prompts directory (default: {_DEFAULT_PROMPTS_DIR})",
    )
    p_prompt.add_argument(
        "--constraints",
        default=None,
        help="Override constraints JSON (default: derived from --profile)",
    )

    # run subcommand
    p_run = subparsers.add_parser(
        "run", help="Run ETL pipeline on JSONL from web UI output (phase 2)"
    )
    p_run.add_argument(
        "--profile",
        default=None,
        help=f"Profile name under {_PROFILES_BASE}/ (default: {_DEFAULT_PROFILE})",
    )
    p_run.add_argument("--input", required=True, help="Input JSONL (raw records from web UI)")
    p_run.add_argument("--output", required=True, help="Output JSONL (scored records)")
    p_run.add_argument(
        "--constraints",
        default=None,
        help="Override constraints JSON (default: derived from --profile)",
    )

    args = parser.parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.command == "prompt":
        return cmd_prompt(args)
    return cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
