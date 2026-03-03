"""API-handler tests for POST /v1/gen-cv error policy and candidate mapping."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from structured_search.api.app import post_gen_cv
from structured_search.contracts import GenCVRequest
from structured_search.tasks.gen_cv.models import GeneratedCV


def _minimal_job() -> dict:
    return {
        "id": "job-001",
        "title": "Senior Backend Engineer",
        "company": "Acme",
        "stack": ["Python", "FastAPI"],
    }


def test_gen_cv_accepts_scored_job_shape_seniority_object():
    request = GenCVRequest(
        profile_id="profile_1",
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
    res = post_gen_cv(request)
    body = res.model_dump(mode="json")
    assert "cv_markdown" in body
    assert isinstance(body.get("generated_cv_json"), dict)


def test_gen_cv_autogenerates_candidate_id_when_missing():
    request = GenCVRequest(
        profile_id="profile_1",
        job=_minimal_job(),
        # canonical profile shape: seniority as string, no id (auto-generated)
        candidate_profile={
            "name": "Jane Doe",
            "seniority": "junior",
            "spoken_languages": ["es", "en"],
        },
    )
    res = post_gen_cv(request)
    body = res.model_dump(mode="json")
    assert "cv_markdown" in body
    assert isinstance(body.get("generated_cv_json"), dict)
    assert body["generated_cv_json"]["candidate_id"] == "profile_1_candidate"


def test_gen_cv_invalid_candidate_returns_422():
    request = GenCVRequest(
        profile_id="profile_1",
        job=_minimal_job(),
        candidate_profile={"name": "Jane Doe", "seniority": ""},
    )
    with pytest.raises(HTTPException) as exc:
        post_gen_cv(request)
    assert exc.value.status_code == 422
    assert "seniority" in str(exc.value.detail).lower()


def test_gen_cv_profile_not_found_returns_404():
    request = GenCVRequest(
        profile_id="does-not-exist",
        job=_minimal_job(),
        candidate_profile={"id": "cand-1", "seniority": "senior"},
    )
    with pytest.raises(HTTPException) as exc:
        post_gen_cv(request)
    assert exc.value.status_code == 404


def test_gen_cv_runtime_error_returns_503(monkeypatch):
    import structured_search.api.app as app_module

    def _boom(**_kwargs):
        raise RuntimeError("llm unavailable")

    monkeypatch.setattr(app_module, "gen_cv", _boom)
    request = GenCVRequest(
        profile_id="profile_1",
        job=_minimal_job(),
        candidate_profile={"id": "cand-1", "seniority": "senior"},
    )
    with pytest.raises(HTTPException) as exc:
        post_gen_cv(request)
    assert exc.value.status_code == 503
    assert "llm unavailable" in str(exc.value.detail)


def test_gen_cv_can_disable_mock_fallback(monkeypatch):
    import structured_search.application.gen_cv.generate_cv as gen_cv_app

    def _boom(*_args, **_kwargs):
        raise RuntimeError("ollama down")

    monkeypatch.setattr(gen_cv_app, "OllamaLLM", _boom)
    request = GenCVRequest(
        profile_id="profile_1",
        job=_minimal_job(),
        candidate_profile={"id": "cand-1", "seniority": "senior"},
        allow_mock_fallback=False,
    )
    with pytest.raises(HTTPException) as exc:
        post_gen_cv(request)
    assert exc.value.status_code == 503
    assert "mock fallback disabled" in str(exc.value.detail).lower()


def test_gen_cv_falls_back_when_ollama_generation_fails(monkeypatch):
    import structured_search.application.gen_cv.generate_cv as gen_cv_app

    class _FakeOllama:
        def __init__(self, model="lfm2.5-thinking", base_url="http://localhost:11434"):
            self.model = model
            self.base_url = base_url

    def _fake_generate(self, job, candidate, allowed_claim_ids=None):
        if isinstance(self.llm, gen_cv_app.MockLLM):
            return GeneratedCV(
                id=f"{job.id}__{candidate.id}",
                source="mock-llm",
                job_id=job.id,
                candidate_id=candidate.id,
                summary="ok",
                grounded_claim_ids=allowed_claim_ids or [],
            )
        raise RuntimeError("model not found")

    monkeypatch.setattr(gen_cv_app, "OllamaLLM", _FakeOllama)
    monkeypatch.setattr(gen_cv_app.GenCVService, "generate", _fake_generate)

    request = GenCVRequest(
        profile_id="profile_1",
        job=_minimal_job(),
        candidate_profile={"id": "cand-1", "seniority": "senior"},
    )
    res = post_gen_cv(request)
    body = res.model_dump(mode="json")
    assert body["model_info"]["fallback_used"] is True
    assert body["generated_cv_json"]["source"] == "mock-llm"


def test_gen_cv_falls_back_when_ollama_returns_empty_content(monkeypatch):
    import structured_search.application.gen_cv.generate_cv as gen_cv_app

    class _FakeOllama:
        def __init__(self, model="lfm2.5-thinking", base_url="http://localhost:11434"):
            self.model = model
            self.base_url = base_url

    def _fake_generate(self, job, candidate, allowed_claim_ids=None):
        if isinstance(self.llm, gen_cv_app.MockLLM):
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
            source="ollama-llm",
            job_id=job.id,
            candidate_id=candidate.id,
            summary="",
            highlights=[],
            grounded_claim_ids=allowed_claim_ids or [],
        )

    monkeypatch.setattr(gen_cv_app, "OllamaLLM", _FakeOllama)
    monkeypatch.setattr(gen_cv_app.GenCVService, "generate", _fake_generate)

    request = GenCVRequest(
        profile_id="profile_1",
        job=_minimal_job(),
        candidate_profile={"id": "cand-1", "seniority": "senior"},
    )
    res = post_gen_cv(request)
    body = res.model_dump(mode="json")
    assert body["model_info"]["fallback_used"] is True
    assert body["generated_cv_json"]["summary"] == "fallback summary"


def test_gen_cv_falls_back_when_ollama_returns_placeholder_content(monkeypatch):
    import structured_search.application.gen_cv.generate_cv as gen_cv_app

    class _FakeOllama:
        def __init__(self, model="lfm2.5-thinking", base_url="http://localhost:11434"):
            self.model = model
            self.base_url = base_url

    def _fake_generate(self, job, candidate, allowed_claim_ids=None):
        if isinstance(self.llm, gen_cv_app.MockLLM):
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
            source="ollama-llm",
            job_id=job.id,
            candidate_id=candidate.id,
            summary="No data provided.",
            highlights=["N/A"],
            grounded_claim_ids=allowed_claim_ids or [],
        )

    monkeypatch.setattr(gen_cv_app, "OllamaLLM", _FakeOllama)
    monkeypatch.setattr(gen_cv_app.GenCVService, "generate", _fake_generate)

    request = GenCVRequest(
        profile_id="profile_1",
        job=_minimal_job(),
        candidate_profile={"id": "cand-1", "seniority": "senior"},
    )
    res = post_gen_cv(request)
    body = res.model_dump(mode="json")
    assert body["model_info"]["fallback_used"] is True
    assert body["generated_cv_json"]["summary"] == "fallback summary"


def test_gen_cv_passes_selected_claim_ids_to_service_generate(monkeypatch):
    import structured_search.application.gen_cv.generate_cv as gen_cv_app

    captured: dict[str, list[str] | None] = {"allowed_claim_ids": None}

    def _fake_generate(self, job, candidate, allowed_claim_ids=None):
        captured["allowed_claim_ids"] = allowed_claim_ids
        return GeneratedCV(
            id=f"{job.id}__{candidate.id}",
            source="fake-llm",
            job_id=job.id,
            candidate_id=candidate.id,
            summary="ok",
            grounded_claim_ids=allowed_claim_ids or [],
        )

    monkeypatch.setattr(gen_cv_app.GenCVService, "generate", _fake_generate)

    request = GenCVRequest(
        profile_id="profile_1",
        job=_minimal_job(),
        candidate_profile={"id": "cand-1", "seniority": "senior"},
        selected_claim_ids=["CLM-1", "CLM-2"],
    )
    res = post_gen_cv(request)
    body = res.model_dump(mode="json")
    assert captured["allowed_claim_ids"] == ["CLM-1", "CLM-2"]
    assert body["generated_cv_json"]["grounded_claim_ids"] == ["CLM-1", "CLM-2"]


def test_gen_cv_passes_llm_model_to_ollama(monkeypatch):
    import structured_search.application.gen_cv.generate_cv as gen_cv_app

    captured: dict[str, str | None] = {"llm_model": None}

    class _FakeOllama:
        def __init__(self, model="lfm2.5-thinking", base_url="http://localhost:11434"):
            captured["llm_model"] = model
            self.model = model
            self.base_url = base_url

    def _fake_generate(self, job, candidate, allowed_claim_ids=None):
        return GeneratedCV(
            id=f"{job.id}__{candidate.id}",
            source="fake-llm",
            job_id=job.id,
            candidate_id=candidate.id,
            summary="ok",
            grounded_claim_ids=allowed_claim_ids or [],
        )

    monkeypatch.setattr(gen_cv_app, "OllamaLLM", _FakeOllama)
    monkeypatch.setattr(gen_cv_app.GenCVService, "generate", _fake_generate)

    request = GenCVRequest(
        profile_id="profile_1",
        job=_minimal_job(),
        candidate_profile={"id": "cand-1", "seniority": "senior"},
        llm_model="mistral",
    )
    post_gen_cv(request)
    assert captured["llm_model"] == "mistral"


def test_gen_cv_preserves_availability_days_zero(monkeypatch):
    import structured_search.application.gen_cv.generate_cv as gen_cv_app

    captured: dict[str, int | None] = {"availability_days": None}

    class _FakeOllama:
        def __init__(self, model="lfm2.5-thinking", base_url="http://localhost:11434"):
            self.model = model
            self.base_url = base_url

    def _fake_generate(self, job, candidate, allowed_claim_ids=None):
        captured["availability_days"] = candidate.availability_days
        return GeneratedCV(
            id=f"{job.id}__{candidate.id}",
            source="fake-llm",
            job_id=job.id,
            candidate_id=candidate.id,
            summary="ok",
            grounded_claim_ids=allowed_claim_ids or [],
        )

    monkeypatch.setattr(gen_cv_app, "OllamaLLM", _FakeOllama)
    monkeypatch.setattr(gen_cv_app.GenCVService, "generate", _fake_generate)

    request = GenCVRequest(
        profile_id="profile_1",
        job=_minimal_job(),
        candidate_profile={
            "id": "cand-1",
            "seniority": "senior",
            "availability_days": 0,
        },
    )
    post_gen_cv(request)
    assert captured["availability_days"] == 0


def test_gen_cv_uses_env_model_and_base_url_when_not_provided(monkeypatch):
    import structured_search.application.gen_cv.generate_cv as gen_cv_app

    captured: dict[str, str | None] = {"llm_model": None, "base_url": None}

    class _FakeOllama:
        def __init__(self, model="lfm2.5-thinking", base_url="http://localhost:11434"):
            captured["llm_model"] = model
            captured["base_url"] = base_url
            self.model = model

    def _fake_generate(self, job, candidate, allowed_claim_ids=None):
        return GeneratedCV(
            id=f"{job.id}__{candidate.id}",
            source="fake-llm",
            job_id=job.id,
            candidate_id=candidate.id,
            summary="ok",
            grounded_claim_ids=allowed_claim_ids or [],
        )

    monkeypatch.delenv("STRUCTURED_SEARCH_LLM_MODEL", raising=False)
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:latest")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.setattr(gen_cv_app, "OllamaLLM", _FakeOllama)
    monkeypatch.setattr(gen_cv_app.GenCVService, "generate", _fake_generate)

    request = GenCVRequest(
        profile_id="profile_1",
        job=_minimal_job(),
        candidate_profile={"id": "cand-1", "seniority": "senior"},
    )
    post_gen_cv(request)
    assert captured["llm_model"] == "qwen2.5:latest"
    assert captured["base_url"] == "http://127.0.0.1:11434"
