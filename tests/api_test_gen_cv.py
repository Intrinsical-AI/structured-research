"""API-handler tests for POST /v1/gen-cv error policy and candidate mapping."""

from __future__ import annotations

from typing import ClassVar

import pytest
from fastapi import HTTPException

from structured_search.api.app import post_action_gen_cv
from structured_search.contracts import GenCVRequest
from structured_search.domain.gen_cv.models import GeneratedCV
from structured_search.infra.llm import MockLLM


def _minimal_job() -> dict:
    return {
        "id": "job-001",
        "title": "Senior Backend Engineer",
        "company": "Acme",
        "stack": ["Python", "FastAPI"],
    }


def _fake_generate_ok(self, job, candidate, allowed_claim_ids=None):
    return GeneratedCV(
        id=f"{job.id}__{candidate.id}",
        source="fake-llm",
        job_id=job.id,
        candidate_id=candidate.id,
        summary="ok",
        grounded_claim_ids=allowed_claim_ids or [],
    )


def test_gen_cv_accepts_scored_job_shape_seniority_object():
    request = GenCVRequest(
        profile_id="profile_example",
        job={
            **_minimal_job(),
            "seniority": {"level": "junior"},
            "modality": "on_site",
        },
        candidate_profile={
            "name": "Jane Doe",
            "seniority": "junior",
            "spoken_languages": ["es", "en"],
        },
    )
    res = post_action_gen_cv("gen_cv", request)
    body = res.model_dump(mode="json")
    assert "cv_markdown" in body
    assert isinstance(body.get("generated_cv_json"), dict)


def test_gen_cv_autogenerates_candidate_id_when_missing():
    request = GenCVRequest(
        profile_id="profile_example",
        job=_minimal_job(),
        candidate_profile={
            "name": "Jane Doe",
            "seniority": "junior",
            "spoken_languages": ["es", "en"],
        },
    )
    res = post_action_gen_cv("gen_cv", request)
    body = res.model_dump(mode="json")
    assert "cv_markdown" in body
    assert isinstance(body.get("generated_cv_json"), dict)
    assert body["generated_cv_json"]["candidate_id"] == "profile_example_candidate"


def test_gen_cv_invalid_candidate_returns_422():
    request = GenCVRequest(
        profile_id="profile_example",
        job=_minimal_job(),
        candidate_profile={"name": "Jane Doe", "seniority": ""},
    )
    with pytest.raises(HTTPException) as exc:
        post_action_gen_cv("gen_cv", request)
    assert exc.value.status_code == 422
    assert "seniority" in str(exc.value.detail).lower()


def test_gen_cv_profile_not_found_returns_404():
    request = GenCVRequest(
        profile_id="does-not-exist",
        job=_minimal_job(),
        candidate_profile={"id": "cand-1", "seniority": "senior"},
    )
    with pytest.raises(HTTPException) as exc:
        post_action_gen_cv("gen_cv", request)
    assert exc.value.status_code == 404


def test_gen_cv_runtime_error_returns_503(monkeypatch):
    import structured_search.api.app as app_module

    def _boom(**_kwargs):
        raise RuntimeError("llm unavailable")

    class _FakePlugin:
        action_handlers: ClassVar[dict[str, object]] = {"gen-cv": _boom}

        @staticmethod
        def supports(capability: str) -> bool:
            return capability == "action:gen-cv"

    monkeypatch.setattr(app_module, "_require_capability", lambda *_args, **_kwargs: _FakePlugin())
    request = GenCVRequest(
        profile_id="profile_example",
        job=_minimal_job(),
        candidate_profile={"id": "cand-1", "seniority": "senior"},
    )
    with pytest.raises(HTTPException) as exc:
        post_action_gen_cv("gen_cv", request)
    assert exc.value.status_code == 503
    assert "llm unavailable" in str(exc.value.detail)


def test_gen_cv_can_disable_mock_fallback(monkeypatch):
    import structured_search.application.gen_cv.generate_cv as gen_cv_app

    def _boom(*_args, **_kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(gen_cv_app, "build_llm", _boom)
    request = GenCVRequest(
        profile_id="profile_example",
        job=_minimal_job(),
        candidate_profile={"id": "cand-1", "seniority": "senior"},
        allow_mock_fallback=False,
    )
    with pytest.raises(HTTPException) as exc:
        post_action_gen_cv("gen_cv", request)
    assert exc.value.status_code == 503
    assert "mock fallback disabled" in str(exc.value.detail).lower()


def test_gen_cv_falls_back_when_llm_instantiation_fails(monkeypatch):
    import structured_search.application.gen_cv.generate_cv as gen_cv_app

    def _boom(*_args, **_kwargs):
        raise RuntimeError("model not found")

    monkeypatch.setattr(gen_cv_app, "build_llm", _boom)
    monkeypatch.setattr(gen_cv_app.GenCVService, "generate", _fake_generate_ok)

    request = GenCVRequest(
        profile_id="profile_example",
        job=_minimal_job(),
        candidate_profile={"id": "cand-1", "seniority": "senior"},
    )
    res = post_action_gen_cv("gen_cv", request)
    body = res.model_dump(mode="json")
    assert body["model_info"]["fallback_used"] is True


def test_gen_cv_falls_back_when_llm_generation_fails(monkeypatch):
    import structured_search.application.gen_cv.generate_cv as gen_cv_app

    fake_llm = MockLLM()
    monkeypatch.setattr(gen_cv_app, "build_llm", lambda *_a, **_k: fake_llm)

    call_count = 0

    def _failing_then_mock(self, job, candidate, allowed_claim_ids=None):
        nonlocal call_count
        call_count += 1
        if isinstance(self.llm, MockLLM) and self.llm is not fake_llm:
            return GeneratedCV(
                id=f"{job.id}__{candidate.id}",
                source="mock-llm",
                job_id=job.id,
                candidate_id=candidate.id,
                summary="fallback ok",
                grounded_claim_ids=allowed_claim_ids or [],
            )
        raise RuntimeError("generation failed")

    monkeypatch.setattr(gen_cv_app.GenCVService, "generate", _failing_then_mock)

    request = GenCVRequest(
        profile_id="profile_example",
        job=_minimal_job(),
        candidate_profile={"id": "cand-1", "seniority": "senior"},
    )
    res = post_action_gen_cv("gen_cv", request)
    body = res.model_dump(mode="json")
    assert body["model_info"]["fallback_used"] is True
    assert body["generated_cv_json"]["summary"] == "fallback ok"


def test_gen_cv_falls_back_when_llm_returns_empty_content(monkeypatch):
    import structured_search.application.gen_cv.generate_cv as gen_cv_app

    fake_llm = MockLLM()
    monkeypatch.setattr(gen_cv_app, "build_llm", lambda *_a, **_k: fake_llm)

    def _empty_then_mock(self, job, candidate, allowed_claim_ids=None):
        if isinstance(self.llm, MockLLM) and self.llm is not fake_llm:
            return GeneratedCV(
                id=f"{job.id}__{candidate.id}",
                source="mock-llm",
                job_id=job.id,
                candidate_id=candidate.id,
                summary="fallback summary",
                highlights=["fallback highlight"],
                grounded_claim_ids=allowed_claim_ids or [],
            )
        return GeneratedCV(
            id=f"{job.id}__{candidate.id}",
            source="real-llm",
            job_id=job.id,
            candidate_id=candidate.id,
            summary="",
            highlights=[],
            grounded_claim_ids=allowed_claim_ids or [],
        )

    monkeypatch.setattr(gen_cv_app.GenCVService, "generate", _empty_then_mock)

    request = GenCVRequest(
        profile_id="profile_example",
        job=_minimal_job(),
        candidate_profile={"id": "cand-1", "seniority": "senior"},
    )
    res = post_action_gen_cv("gen_cv", request)
    body = res.model_dump(mode="json")
    assert body["model_info"]["fallback_used"] is True
    assert body["generated_cv_json"]["summary"] == "fallback summary"


def test_gen_cv_falls_back_when_llm_returns_placeholder_content(monkeypatch):
    import structured_search.application.gen_cv.generate_cv as gen_cv_app

    fake_llm = MockLLM()
    monkeypatch.setattr(gen_cv_app, "build_llm", lambda *_a, **_k: fake_llm)

    def _placeholder_then_mock(self, job, candidate, allowed_claim_ids=None):
        if isinstance(self.llm, MockLLM) and self.llm is not fake_llm:
            return GeneratedCV(
                id=f"{job.id}__{candidate.id}",
                source="mock-llm",
                job_id=job.id,
                candidate_id=candidate.id,
                summary="fallback summary",
                highlights=["fallback highlight"],
                grounded_claim_ids=allowed_claim_ids or [],
            )
        return GeneratedCV(
            id=f"{job.id}__{candidate.id}",
            source="real-llm",
            job_id=job.id,
            candidate_id=candidate.id,
            summary="No data provided.",
            highlights=["N/A"],
            grounded_claim_ids=allowed_claim_ids or [],
        )

    monkeypatch.setattr(gen_cv_app.GenCVService, "generate", _placeholder_then_mock)

    request = GenCVRequest(
        profile_id="profile_example",
        job=_minimal_job(),
        candidate_profile={"id": "cand-1", "seniority": "senior"},
    )
    res = post_action_gen_cv("gen_cv", request)
    body = res.model_dump(mode="json")
    assert body["model_info"]["fallback_used"] is True
    assert body["generated_cv_json"]["summary"] == "fallback summary"


def test_gen_cv_passes_selected_claim_ids_to_service_generate(monkeypatch):
    import structured_search.application.gen_cv.generate_cv as gen_cv_app

    captured: dict[str, list[str] | None] = {"allowed_claim_ids": None}

    def _capture_generate(self, job, candidate, allowed_claim_ids=None):
        captured["allowed_claim_ids"] = allowed_claim_ids
        return GeneratedCV(
            id=f"{job.id}__{candidate.id}",
            source="fake-llm",
            job_id=job.id,
            candidate_id=candidate.id,
            summary="ok",
            grounded_claim_ids=allowed_claim_ids or [],
        )

    monkeypatch.setattr(gen_cv_app.GenCVService, "generate", _capture_generate)

    request = GenCVRequest(
        profile_id="profile_example",
        job=_minimal_job(),
        candidate_profile={"id": "cand-1", "seniority": "senior"},
        selected_claim_ids=["CLM-1", "CLM-2"],
    )
    res = post_action_gen_cv("gen_cv", request)
    body = res.model_dump(mode="json")
    assert captured["allowed_claim_ids"] == ["CLM-1", "CLM-2"]
    assert body["generated_cv_json"]["grounded_claim_ids"] == ["CLM-1", "CLM-2"]


def test_gen_cv_passes_model_to_build_llm(monkeypatch):
    import structured_search.application.gen_cv.generate_cv as gen_cv_app

    captured: dict[str, str | None] = {"model": None, "provider": None}

    def _fake_build_llm(provider, model=None, **_kwargs):
        captured["provider"] = provider
        captured["model"] = model
        return MockLLM()

    monkeypatch.setattr(gen_cv_app, "build_llm", _fake_build_llm)
    monkeypatch.setattr(gen_cv_app.GenCVService, "generate", _fake_generate_ok)

    request = GenCVRequest(
        profile_id="profile_example",
        job=_minimal_job(),
        candidate_profile={"id": "cand-1", "seniority": "senior"},
        llm_model="mistral",
    )
    post_action_gen_cv("gen_cv", request)
    assert captured["model"] == "mistral"
    assert captured["provider"] == "ollama"  # default provider


def test_gen_cv_respects_provider_env_var(monkeypatch):
    import structured_search.application.gen_cv.generate_cv as gen_cv_app

    captured: dict[str, str | None] = {"provider": None}

    def _fake_build_llm(provider, model=None, **_kwargs):
        captured["provider"] = provider
        return MockLLM()

    monkeypatch.setenv("STRUCTURED_SEARCH_LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("STRUCTURED_SEARCH_LLM_MODEL", raising=False)
    monkeypatch.setattr(gen_cv_app, "build_llm", _fake_build_llm)
    monkeypatch.setattr(gen_cv_app.GenCVService, "generate", _fake_generate_ok)

    request = GenCVRequest(
        profile_id="profile_example",
        job=_minimal_job(),
        candidate_profile={"id": "cand-1", "seniority": "senior"},
    )
    post_action_gen_cv("gen_cv", request)
    assert captured["provider"] == "anthropic"


def test_gen_cv_respects_model_env_var(monkeypatch):
    import structured_search.application.gen_cv.generate_cv as gen_cv_app

    captured: dict[str, str | None] = {"model": None}

    def _fake_build_llm(provider, model=None, **_kwargs):
        captured["model"] = model
        return MockLLM()

    monkeypatch.setenv("STRUCTURED_SEARCH_LLM_MODEL", "qwen2.5:latest")
    monkeypatch.delenv("STRUCTURED_SEARCH_LLM_PROVIDER", raising=False)
    monkeypatch.setattr(gen_cv_app, "build_llm", _fake_build_llm)
    monkeypatch.setattr(gen_cv_app.GenCVService, "generate", _fake_generate_ok)

    request = GenCVRequest(
        profile_id="profile_example",
        job=_minimal_job(),
        candidate_profile={"id": "cand-1", "seniority": "senior"},
    )
    post_action_gen_cv("gen_cv", request)
    assert captured["model"] == "qwen2.5:latest"


def test_gen_cv_preserves_availability_days_zero(monkeypatch):
    import structured_search.application.gen_cv.generate_cv as gen_cv_app

    captured: dict[str, int | None] = {"availability_days": None}

    def _capture_generate(self, job, candidate, allowed_claim_ids=None):
        captured["availability_days"] = candidate.availability_days
        return GeneratedCV(
            id=f"{job.id}__{candidate.id}",
            source="fake-llm",
            job_id=job.id,
            candidate_id=candidate.id,
            summary="ok",
            grounded_claim_ids=allowed_claim_ids or [],
        )

    monkeypatch.setattr(gen_cv_app.GenCVService, "generate", _capture_generate)

    request = GenCVRequest(
        profile_id="profile_example",
        job=_minimal_job(),
        candidate_profile={
            "id": "cand-1",
            "seniority": "senior",
            "availability_days": 0,
        },
    )
    post_action_gen_cv("gen_cv", request)
    assert captured["availability_days"] == 0
