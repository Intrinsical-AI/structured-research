"""Unit tests for application.gen_cv use-case orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from structured_search.application.common.dependencies import ApplicationDependencies
from structured_search.application.gen_cv.generate_cv import (
    _coerce_job_seniority,
    _coerce_seniority,
    gen_cv,
)
from structured_search.infra.llm import MockLLM
from structured_search.infra.loading import TolerantJSONLParser
from structured_search.infra.persistence_fs import (
    FilesystemProfileRepository,
    FilesystemRunRepository,
)
from structured_search.ports.persistence import BundleData


def _deps(tmp_path: Path) -> ApplicationDependencies:
    profile_repo = FilesystemProfileRepository(base_dir=tmp_path / "profiles")
    profile_repo.save_bundle(
        "gen_cv",
        "profile_example",
        BundleData(
            constraints={"domain": "gen_cv", "must": [], "prefer": [], "avoid": []},
            task={
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
            task_config={"runtime": {"llm": {"model": "mistral"}}},
            user_profile=None,
        ),
    )
    return ApplicationDependencies(
        profile_repo=profile_repo,
        run_repo=FilesystemRunRepository(base_dir=tmp_path / "runs"),
        prompts_dir=Path("resources/prompts"),
        jsonl_parser=TolerantJSONLParser(),
    )


def _job() -> dict:
    return {
        "id": "job-001",
        "title": "Senior Backend Engineer",
        "company": "Acme",
        "stack": ["Python", "FastAPI"],
    }


def test_gen_cv_uses_fallback_when_ollama_is_unavailable(tmp_path: Path):
    class _BrokenOllama:
        def __init__(self, model: str, base_url: str):
            raise RuntimeError("ollama unavailable")

    result = gen_cv(
        profile_id="profile_example",
        job=_job(),
        candidate_profile={"id": "cand-1", "seniority": "senior"},
        deps=_deps(tmp_path),
        ollama_llm_cls=_BrokenOllama,
        mock_llm_cls=MockLLM,
    )

    payload = result.model_dump(mode="json")
    assert payload["model_info"]["fallback_used"] is True
    assert payload["generated_cv_json"]["summary"]


def test_gen_cv_rejects_missing_seniority(tmp_path: Path):
    with pytest.raises(ValueError):
        gen_cv(
            profile_id="profile_example",
            job=_job(),
            candidate_profile={"id": "cand-1"},
            deps=_deps(tmp_path),
        )


def test_gen_cv_raises_when_mock_fallback_disabled(tmp_path: Path):
    class _BrokenOllama:
        def __init__(self, model: str, base_url: str):
            raise RuntimeError("ollama unavailable")

    with pytest.raises(RuntimeError):
        gen_cv(
            profile_id="profile_example",
            job=_job(),
            candidate_profile={"id": "cand-1", "seniority": "senior"},
            allow_mock_fallback=False,
            deps=_deps(tmp_path),
            ollama_llm_cls=_BrokenOllama,
            mock_llm_cls=MockLLM,
        )


# ---------------------------------------------------------------------------
# _coerce_seniority — edge cases
# ---------------------------------------------------------------------------


class TestCoerceSeniority:
    def test_none_raises(self):
        with pytest.raises(ValueError, match="seniority is required"):
            _coerce_seniority(None)

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="seniority is required"):
            _coerce_seniority("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="seniority is required"):
            _coerce_seniority("   ")

    def test_valid_string_returned_stripped(self):
        assert _coerce_seniority("  senior  ") == "senior"

    def test_non_standard_alias_returned_as_is(self):
        assert _coerce_seniority("principal") == "principal"


# ---------------------------------------------------------------------------
# _coerce_job_seniority — edge cases
# ---------------------------------------------------------------------------


class TestCoerceJobSeniority:
    def test_none_returns_none(self):
        assert _coerce_job_seniority(None) is None

    def test_empty_string_returns_none(self):
        assert _coerce_job_seniority("") is None

    def test_whitespace_only_returns_none(self):
        assert _coerce_job_seniority("   ") is None

    def test_valid_string_returned_stripped(self):
        assert _coerce_job_seniority("  mid  ") == "mid"

    def test_list_returns_first_valid(self):
        assert _coerce_job_seniority(["senior", "mid"]) == "senior"

    def test_list_skips_empty_and_returns_first_valid(self):
        assert _coerce_job_seniority(["", "  ", "mid"]) == "mid"

    def test_list_all_empty_returns_none(self):
        assert _coerce_job_seniority(["", "  "]) is None

    def test_dict_with_level_returns_stripped(self):
        assert _coerce_job_seniority({"level": "  senior  "}) == "senior"

    def test_dict_without_level_returns_none(self):
        assert _coerce_job_seniority({"rank": "senior"}) is None

    def test_unexpected_type_returns_none(self):
        assert _coerce_job_seniority(42) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# gen_cv — generation-failure fallback paths
# ---------------------------------------------------------------------------


class _OllamaBuildsButFails:
    """Stub LLM: constructs fine but raises on every call."""

    model = "stub-model"

    def __init__(self, model: str, base_url: str):
        pass  # constructor succeeds

    def extract_json(self, prompt: str, schema: Any) -> Any:
        raise RuntimeError("Ollama generation unavailable")


def test_gen_cv_uses_fallback_when_generation_fails(tmp_path: Path):
    """Constructor OK, but generation raises → MockLLM fallback used."""
    result = gen_cv(
        profile_id="profile_example",
        job=_job(),
        candidate_profile={"id": "cand-1", "seniority": "senior"},
        allow_mock_fallback=True,
        deps=_deps(tmp_path),
        ollama_llm_cls=_OllamaBuildsButFails,
        mock_llm_cls=MockLLM,
    )
    payload = result.model_dump(mode="json")
    assert payload["model_info"]["fallback_used"] is True
    assert payload["generated_cv_json"]["summary"]


def test_gen_cv_raises_when_generation_fails_and_fallback_disabled(tmp_path: Path):
    """Constructor OK, generation raises, mock fallback disabled → RuntimeError propagated."""
    with pytest.raises(RuntimeError, match="mock fallback disabled"):
        gen_cv(
            profile_id="profile_example",
            job=_job(),
            candidate_profile={"id": "cand-1", "seniority": "senior"},
            allow_mock_fallback=False,
            deps=_deps(tmp_path),
            ollama_llm_cls=_OllamaBuildsButFails,
            mock_llm_cls=MockLLM,
        )
