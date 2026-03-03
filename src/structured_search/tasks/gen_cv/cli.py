#!/usr/bin/env python3
"""CLI: GEN_CV workflows.

Usage:
  structured-search gen-cv run --job job.json --candidate profile.json
  structured-search gen-cv prompt --job job.json --candidate profile.json
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from pydantic import ValidationError

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_DEFAULT_PROFILE = "profile_1"
_PROFILES_BASE = "config/job_search"
_DEFAULT_PROMPTS_DIR = "resources/prompts"


def _profile_atoms_dir(profile: str) -> Path:
    return Path(_PROFILES_BASE) / profile / "atoms"


def _resolve_base_output_path(prompt_output: Path, base_output: str | None) -> Path:
    if base_output:
        return Path(base_output)
    if prompt_output.suffix:
        return prompt_output.with_name(f"{prompt_output.stem}.base{prompt_output.suffix}")
    return prompt_output.parent / f"{prompt_output.name}.base.md"


def _load_job(path: str):
    from structured_search.tasks.gen_cv.models import (
        JobDescription,
    )

    try:
        with open(path, encoding="utf-8") as f:
            job = JobDescription.model_validate(json.load(f))
    except FileNotFoundError:
        logger.error(f"Job description file not found: {path}")
        return None
    except (json.JSONDecodeError, ValidationError) as e:
        logger.error(f"Invalid job description file '{path}': {e}")
        return None
    return job


def _load_candidate(path: str):
    from structured_search.tasks.gen_cv.models import (
        CandidateAtomsProfile,
    )

    try:
        with open(path, encoding="utf-8") as f:
            candidate = CandidateAtomsProfile.model_validate(json.load(f))
    except FileNotFoundError:
        logger.error(f"Candidate profile file not found: {path}")
        return None
    except (json.JSONDecodeError, ValidationError) as e:
        logger.error(f"Invalid candidate profile file '{path}': {e}")
        return None
    return candidate


def cmd_prompt(args) -> int:
    """Render GEN_CV prompt with grounded atoms and export it to Markdown."""
    from structured_search.infra.grounding import AtomsGrounding
    from structured_search.infra.llm import MockLLM
    from structured_search.infra.prompts import PromptComposer
    from structured_search.tasks.gen_cv.service import GenCVService

    job = _load_job(args.job)
    candidate = _load_candidate(args.candidate)
    if job is None or candidate is None:
        return 1

    profile = args.profile or _DEFAULT_PROFILE
    atoms_dir = Path(args.atoms_dir) if args.atoms_dir else _profile_atoms_dir(profile)
    if not atoms_dir.is_dir():
        logger.error(f"Atoms directory not found: {atoms_dir}")
        return 1

    prompts_dir = Path(args.prompts_dir or _DEFAULT_PROMPTS_DIR)
    if not prompts_dir.is_dir():
        logger.error(f"Prompts directory not found: {prompts_dir}")
        return 1

    try:
        artifacts = GenCVService(
            llm=MockLLM(),
            grounding=AtomsGrounding(atoms_dir=str(atoms_dir)),
            prompt_composer=PromptComposer(prompts_dir),
        ).render_prompt(
            job=job,
            candidate=candidate,
            allowed_claim_ids=args.allowed_claim_id,
        )
    except Exception as e:
        logger.error(f"Prompt rendering failed: {e}")
        return 1

    output_path = Path(args.output)
    base_output_path = _resolve_base_output_path(output_path, args.base_output)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    base_output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(artifacts.rendered_prompt, encoding="utf-8")
    base_output_path.write_text(artifacts.base_prompt, encoding="utf-8")

    print("\n GEN_CV prompt exported!")
    print(f"  Job:         {job.title} @ {job.company}")
    print(f"  Candidate:   {candidate.id}")
    print(f"  Profile:     {profile}")
    print(f"  Atoms:       {atoms_dir}")
    print(f"  Prompt MD:   {output_path}")
    print(f"  Base MD:     {base_output_path}")
    return 0


def cmd_run(args) -> int:
    """Generate a CV for a given job description and candidate profile."""
    from structured_search.infra.grounding import AtomsGrounding
    from structured_search.infra.llm import OllamaLLM
    from structured_search.infra.prompts import PromptComposer
    from structured_search.tasks.gen_cv.service import GenCVService

    job = _load_job(args.job)
    candidate = _load_candidate(args.candidate)
    if job is None or candidate is None:
        return 1

    profile = args.profile or _DEFAULT_PROFILE
    atoms_dir = Path(args.atoms_dir) if args.atoms_dir else _profile_atoms_dir(profile)
    if not atoms_dir.is_dir():
        logger.error(f"Atoms directory not found: {atoms_dir}")
        return 1

    prompt_composer = PromptComposer(Path(args.prompts_dir)) if args.prompts_dir else None

    try:
        cv = GenCVService(
            llm=OllamaLLM(model=args.llm_model),
            grounding=AtomsGrounding(atoms_dir=str(atoms_dir)),
            prompt_composer=prompt_composer,
        ).generate(job=job, candidate=candidate)
    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        return 1
    except RuntimeError as e:
        logger.error(f"LLM error: {e}")
        return 1
    except Exception as e:
        logger.error(f"CV generation failed: {e}")
        return 1

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(cv.model_dump(mode="json"), f, indent=2, default=str)

    print("\n CV generated!")
    print(f"  Job:       {job.title} @ {job.company}")
    print(f"  Candidate: {candidate.id}")
    print(f"  Output:    {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="GEN_CV: render/export prompts or generate tailored CVs"
    )
    parser.add_argument("--verbose", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_prompt = subparsers.add_parser(
        "prompt",
        help="Render GEN_CV prompt with atoms embedded and export .md files",
    )
    p_prompt.add_argument("--job", required=True, help="JobDescription JSON file")
    p_prompt.add_argument("--candidate", required=True, help="CandidateAtomsProfile JSON file")
    p_prompt.add_argument(
        "--profile",
        default=None,
        help=f"Profile name under {_PROFILES_BASE}/ (default: {_DEFAULT_PROFILE})",
    )
    p_prompt.add_argument(
        "--atoms-dir",
        default=None,
        help="Override atoms directory (default: derived from --profile)",
    )
    p_prompt.add_argument(
        "--prompts-dir",
        default=_DEFAULT_PROMPTS_DIR,
        help=f"Path to prompts directory (default: {_DEFAULT_PROMPTS_DIR})",
    )
    p_prompt.add_argument(
        "--allowed-claim-id",
        action="append",
        default=None,
        help="Restrict grounded claims to specific IDs (repeatable)",
    )
    p_prompt.add_argument(
        "--output",
        default="gen_cv_prompt.md",
        help="Output Markdown file for fully rendered prompt",
    )
    p_prompt.add_argument(
        "--base-output",
        default=None,
        help="Output Markdown file for base prompt snapshot (default: <output>.base.md)",
    )

    p_run = subparsers.add_parser("run", help="Generate a CV (requires a local LLM via Ollama)")
    p_run.add_argument("--job", required=True, help="JobDescription JSON file")
    p_run.add_argument("--candidate", required=True, help="CandidateAtomsProfile JSON file")
    p_run.add_argument(
        "--profile",
        default=None,
        help=f"Profile name under {_PROFILES_BASE}/ (default: {_DEFAULT_PROFILE})",
    )
    p_run.add_argument(
        "--atoms-dir",
        default=None,
        help="Override atoms directory (default: derived from --profile)",
    )
    p_run.add_argument("--llm-model", default="lfm2.5-thinking", help="Ollama model name")
    p_run.add_argument(
        "--prompts-dir",
        default=None,
        help="Path to resources/prompts/ (enables identity grounding)",
    )
    p_run.add_argument("--output", default="cv.json", help="Output GeneratedCV JSON")

    args = parser.parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.command == "prompt":
        return cmd_prompt(args)
    return cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
