"""Scaffold a new task with the canonical config/ layout."""

import argparse
import json
from pathlib import Path


def scaffold_task(task_id: str) -> int:
    """Generate directory structure for a new task.

    Creates:
    - resources/prompts/{task_id}/ (context + steps)
    - config/{task_id}/profile_default/ (bundle.json + atoms)

    Args:
        task_id: Task identifier (e.g., 'candidate_search')

    Returns:
        0 on success, 1 on error
    """
    repo_root = Path(__file__).parent.parent

    # 1. Create prompts directory
    prompts_dir = repo_root / "resources" / "prompts" / task_id
    prompts_dir.mkdir(parents=True, exist_ok=True)

    # Create context.md
    context_path = prompts_dir / "context.md"
    context_path.write_text(
        f"""# {task_id.upper()} Context

## Overview
[TODO: Add overview of the {task_id} task]

## Key Concepts
[TODO: List key concepts and definitions]

## Domain-Specific Rules
[TODO: Add domain-specific validation rules]
"""
    )

    # Create steps
    steps_dir = prompts_dir / "steps"
    steps_dir.mkdir(exist_ok=True)

    steps = {
        "S0_intent.md": "## S0: Intent\n\nIdentify intent and objectives for the task.\n\n[TODO: Add S0 prompt]",
        "S1_clarify.md": "## S1: Clarify\n\nClarify ambiguous configuration.\n\n[TODO: Add S1 prompt (optional)]",
        "S2_propose.md": "## S2: Propose\n\nPropose configuration improvements.\n\n[TODO: Add S2 prompt (optional)]",
        "S3_execute.md": "## S3: Execute\n\nExecute extraction + gates + scoring.\n\n[TODO: Add S3 prompt]",
    }

    for step_name, content in steps.items():
        (steps_dir / step_name).write_text(content)

    # 2. Create config directory
    config_dir = repo_root / "config" / task_id / "profile_default"
    config_dir.mkdir(parents=True, exist_ok=True)

    bundle = {
        "task_id": task_id,
        "profile_id": "profile_default",
        "constraints": {
            "domain": task_id,
            "sources": {"primary": [], "secondary": [], "fallback": []},
            "must": [],
            "prefer": [],
            "avoid": [],
            "limits": {},
            "relaxation": {"order": [], "steps": {}, "emit_constraints_diff": False},
        },
        "task": {
            "gates": {
                "hard_filters_mode": "require_all",
                "hard_filters": [],
                "reject_anomalies": [],
                "required_evidence_fields": [],
            },
            "soft_scoring": {
                "formula_version": "v2_soft_after_gates",
                "prefer_weight_default": 1.0,
                "avoid_penalty_default": 1.0,
                "signal_boost": {},
                "penalties": {},
            },
        },
        "task_config": {
            "agent_name": "USAT",
            "version": "0.1.0",
            "language_priority": ["en"],
            "max_results": 30,
            "target_results": [10, 20],
        },
        "user_profile": {
            "timezone": "UTC",
            "mobility": "flexible",
            "risk_tolerance": "medium",
            "currency_default": "EUR",
            "language_preference": ["en"],
        },
        "domain_schema": None,
        "result_schema": {
            "title": f"{task_id}_result",
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "source": {"type": "string"},
            },
            "required": ["id", "source"],
        },
    }
    (config_dir / "bundle.json").write_text(json.dumps(bundle, indent=2))

    # 3. Create atoms directory
    atoms_dir = config_dir / "atoms"
    atoms_dir.mkdir(exist_ok=True)

    for subdir in ["context", "claims", "evidence", "schemas"]:
        (atoms_dir / subdir).mkdir(exist_ok=True)

    # Create canon_tags template
    (atoms_dir / "canon_tags.yaml").write_text(
        """facets:
  example_facet:
    canonical:
      - value1
      - value2
    aliases:
      alias1: value1
"""
    )

    # 4. Create projects template directory
    projects_dir = config_dir / "projects"
    projects_dir.mkdir(exist_ok=True)

    print(f"✓ Task '{task_id}' scaffolded successfully!\n")
    print("Created:")
    print(f"  📁 resources/prompts/{task_id}/")
    print("     ├── context.md")
    print("     └── steps/ (S0, S1, S2, S3)")
    print(f"\n  📁 config/{task_id}/")
    print("     └── profile_default/")
    print("         ├── bundle.json")
    print("         ├── atoms/ (context, claims, evidence, schemas, canon_tags.yaml)")
    print("         └── projects/")
    print("\nNext steps:")
    print(f"  1. Edit resources/prompts/{task_id}/context.md")
    print(f"  2. Edit resources/prompts/{task_id}/steps/*.md")
    print(f"  3. Edit config/{task_id}/profile_default/bundle.json")
    print(f"  4. Create models in src/structured_search/domain/{task_id}/models.py")
    print("  5. Register plugin in src/structured_search/application/core/plugins/")

    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and scaffold task."""
    parser = argparse.ArgumentParser(description="Scaffold a new task with directory structure")
    parser.add_argument(
        "--task-id",
        required=True,
        help="Task identifier (e.g., 'candidate_search')",
    )

    args = parser.parse_args(argv)

    return scaffold_task(args.task_id)


if __name__ == "__main__":
    raise SystemExit(main())
