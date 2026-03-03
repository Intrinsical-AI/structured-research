"""Unit tests for GEN_CV task CLI."""

from __future__ import annotations

import json
from pathlib import Path

from structured_search.tasks.gen_cv import cli as gen_cv_cli


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _prepare_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    job_path = tmp_path / "job.json"
    candidate_path = tmp_path / "candidate.json"
    atoms_dir = tmp_path / "atoms"
    prompts_dir = tmp_path / "prompts"

    _write_json(
        job_path,
        {
            "id": "job-1",
            "title": "Senior Search Engineer",
            "company": "Acme",
            "stack": ["Python", "RAG"],
        },
    )
    _write_json(candidate_path, {"id": "cand-1", "seniority": "senior"})

    _write_text(
        atoms_dir / "context" / "ctx.yaml",
        (
            "id: ctx-1\n"
            "domain: job_search\n"
            "content: Retrieval and ranking project\n"
            "tags:\n"
            "  - python\n"
            "  - rag\n"
        ),
    )
    _write_text(
        atoms_dir / "claims" / "claim-1.yaml",
        (
            "id: claim-1\n"
            "parent_context_id: ctx-1\n"
            "variants:\n"
            "  technical: Built a production RAG pipeline.\n"
            "defensibility:\n"
            "  evidence_ids:\n"
            "    - ev-1\n"
        ),
    )
    _write_text(
        atoms_dir / "claims" / "claim-2.yaml",
        (
            "id: claim-2\n"
            "parent_context_id: ctx-1\n"
            "variants:\n"
            "  technical: Improved retrieval precision by 20 percent.\n"
            "defensibility:\n"
            "  evidence_ids:\n"
            "    - ev-2\n"
        ),
    )
    _write_text(
        atoms_dir / "evidence" / "ev-1.yaml",
        "id: ev-1\nurl: https://example.com/ev-1\n",
    )
    _write_text(
        atoms_dir / "evidence" / "ev-2.yaml",
        "id: ev-2\nurl: https://example.com/ev-2\n",
    )

    _write_text(prompts_dir / "_base" / "01_identity.md", "CUSTOM GEN_CV IDENTITY")
    return job_path, candidate_path, atoms_dir, prompts_dir


def test_prompt_command_exports_rendered_and_base_markdown(tmp_path: Path):
    job_path, candidate_path, atoms_dir, prompts_dir = _prepare_fixture(tmp_path)
    output = tmp_path / "out" / "gen_cv_prompt.md"

    exit_code = gen_cv_cli.main(
        [
            "prompt",
            "--job",
            str(job_path),
            "--candidate",
            str(candidate_path),
            "--atoms-dir",
            str(atoms_dir),
            "--prompts-dir",
            str(prompts_dir),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert output.is_file()
    base_output = output.with_name("gen_cv_prompt.base.md")
    assert base_output.is_file()

    rendered = output.read_text(encoding="utf-8")
    base = base_output.read_text(encoding="utf-8")
    assert "CUSTOM GEN_CV IDENTITY" in rendered
    assert "[claim-1]" in rendered
    assert "Evidence: https://example.com/ev-1" in rendered
    assert "## Grounded Facts (cite IDs of facts you use)" in rendered
    assert base == "CUSTOM GEN_CV IDENTITY"


def test_prompt_command_filters_claims_with_allowed_claim_id(tmp_path: Path):
    job_path, candidate_path, atoms_dir, prompts_dir = _prepare_fixture(tmp_path)
    output = tmp_path / "out" / "filtered.md"

    exit_code = gen_cv_cli.main(
        [
            "prompt",
            "--job",
            str(job_path),
            "--candidate",
            str(candidate_path),
            "--atoms-dir",
            str(atoms_dir),
            "--prompts-dir",
            str(prompts_dir),
            "--allowed-claim-id",
            "claim-2",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    rendered = output.read_text(encoding="utf-8")
    assert "[claim-2]" in rendered
    assert "[claim-1]" not in rendered
    assert "You may cite ONLY the following claim IDs: claim-2" in rendered
