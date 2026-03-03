"""Shared pytest fixtures."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

import pytest

from structured_search.application.common.dependencies import (
    clear_configured_dependencies,
    configure_filesystem_dependencies,
)
from structured_search.domain import BaseConstraints, BaseResult, ConstraintRule
from structured_search.infra.exporting import MockExporter
from structured_search.infra.loading import MockLoader
from structured_search.infra.scoring import MockScorer
from structured_search.tasks.job_search.models import (
    GeoInfo,
    JobPosting,
    JobSearchConstraints,
    SeniorityInfo,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Absolute path to the repository root."""
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def atoms_dir(repo_root: Path) -> Path:
    """Path to synthetic atoms directory used by integration tests when available."""
    return repo_root / "tests" / "fixtures" / "profiles" / "profile_1" / "atoms"


# ---------------------------------------------------------------------------
# Default app dependencies for tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def configure_default_test_dependencies(repo_root: Path, tmp_path: Path):
    """Point default app dependencies to committed test fixtures."""
    fixture_profiles = repo_root / "tests" / "fixtures" / "profiles"
    sandbox_profiles = tmp_path / "profiles"
    shutil.copytree(fixture_profiles, sandbox_profiles, dirs_exist_ok=True)

    configure_filesystem_dependencies(
        profiles_base=sandbox_profiles,
        runs_dir=tmp_path / "runs",
        prompts_dir=repo_root / "resources" / "prompts",
    )
    yield
    clear_configured_dependencies()


# ---------------------------------------------------------------------------
# Domain primitives
# ---------------------------------------------------------------------------


@pytest.fixture
def base_result() -> BaseResult:
    return BaseResult(id="r_001", source="test")


@pytest.fixture
def base_constraints() -> BaseConstraints:
    return BaseConstraints(domain="test")


@pytest.fixture
def job_constraints() -> JobSearchConstraints:
    return JobSearchConstraints(domain="job_search")


@pytest.fixture
def job_constraints_with_rules() -> JobSearchConstraints:
    return JobSearchConstraints(
        domain="job_search",
        must=[ConstraintRule(field="seniority.level", op="=", value="senior")],
        prefer=[ConstraintRule(field="modality", op="=", value="remote", weight=2.0)],
    )


# ---------------------------------------------------------------------------
# Task models
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_job_posting() -> JobPosting:
    return JobPosting(
        id="job_001",
        source="linkedin",
        company="Acme",
        title="Senior Engineer",
        posted_at=datetime.now(),
        apply_url="https://example.com/apply",
        geo=GeoInfo(region="Europe", city="Berlin"),
        modality="hybrid",
        seniority=SeniorityInfo(level="senior"),
    )


@pytest.fixture
def valid_job_dict() -> dict:
    return {
        "id": "job_001",
        "source": "linkedin",
        "company": "Acme",
        "title": "Senior Engineer",
        "posted_at": datetime.now().isoformat(),
        "apply_url": "https://example.com/apply",
        "geo": {"region": "Europe", "city": "Berlin"},
        "modality": "hybrid",
        "seniority": {"level": "senior"},
    }


# ---------------------------------------------------------------------------
# Mock adapters
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_scorer() -> MockScorer:
    return MockScorer(return_value=7.5, return_gate_passed=True)


@pytest.fixture
def mock_scorer_failing() -> MockScorer:
    return MockScorer(return_value=0.0, return_gate_passed=False)


@pytest.fixture
def mock_exporter() -> MockExporter:
    return MockExporter()


@pytest.fixture
def mock_loader_empty() -> MockLoader:
    return MockLoader([])


@pytest.fixture
def mock_loader_single(valid_job_dict: dict) -> MockLoader:
    return MockLoader([valid_job_dict])
