#!/usr/bin/env python3
"""Compose a full USAT prompt for a task and step.

Thin CLI wrapper around structured_search.infra.prompts.PromptComposer.

Usage:
  python compose.py --task job_search --step S0
  python compose.py --task job_search --step S3 --output /tmp/prompt.md
  python compose.py --task job_search --step S3 --no-base  # context + step only
"""

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Compose USAT prompt from modular parts")
    parser.add_argument("--task", required=True, help="Task name (e.g., job_search)")
    parser.add_argument("--step", required=True, help="Step code (S0, S1, S2, or S3)")
    parser.add_argument("--output", default=None, help="Output file path (default: stdout)")
    parser.add_argument("--no-base", action="store_true", help="Omit base layers")
    args = parser.parse_args()

    prompts_dir = Path(__file__).parent

    # Allow running from repo root without installing the package
    src_dir = prompts_dir.parent.parent / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    try:
        from structured_search.infra.prompts import PromptComposer
    except ImportError:
        print(
            "ERROR: Could not import structured_search. Run from project root with uv.",
            file=sys.stderr,
        )
        return 1

    composer = PromptComposer(prompts_dir)
    prompt = composer.compose(
        task=args.task,
        step=args.step,
        include_base=not args.no_base,
    )

    if not prompt.strip():
        print(
            f"ERROR: No prompt content assembled for task={args.task} step={args.step}",
            file=sys.stderr,
        )
        return 1

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(prompt, encoding="utf-8")
        print(f"✓ Prompt written to {output_path}")
        print(f"  Lines: {len(prompt.splitlines())}")
    else:
        print(prompt)

    return 0


if __name__ == "__main__":
    sys.exit(main())
