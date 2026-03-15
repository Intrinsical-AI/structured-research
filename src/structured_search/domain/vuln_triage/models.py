"""Vulnerability-triage task domain models."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

from structured_search.domain import BaseConstraints, BaseResult

_OSVISH_ID_RE = re.compile(r"^(?:GHSA|PYSEC|GO|RUSTSEC|OSV)-")


def _clean_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return str(value)
    cleaned = value.strip()
    return cleaned or None


def _derive_commit_url(repo_url: str | None, commit_sha: str | None) -> str | None:
    if not repo_url or not commit_sha:
        return None
    return f"{repo_url.rstrip('/')}/commit/{commit_sha}"


def _derive_osv_id(record_id: str | None) -> str | None:
    if not record_id:
        return None
    candidate = record_id.split("_", 1)[0]
    if _OSVISH_ID_RE.match(candidate):
        return candidate
    return None


class VulnTriageTaskRuntimeConfig(BaseModel):
    """Structural validation for vuln_triage task config.

    Ensures required top-level keys are present and are dicts.
    Deep field-level validation happens at scoring time via the infra layer.
    """

    model_config = ConfigDict(extra="allow")

    gates: dict[str, Any]
    soft_scoring: dict[str, Any]


class VulnTriageConstraints(BaseConstraints):
    domain: Literal["vuln_triage"] = "vuln_triage"


class VulnRecord(BaseResult):
    model_config = ConfigDict(extra="allow")

    repo: str | None = None
    repo_url: str | None = None
    language: str | None = None
    file_path: str | None = None
    osv_id: str | None = None
    cve_id: str | None = None
    cwe_id: str | None = None
    commit_vuln: str | None = None
    commit_fix: str | None = None
    commit_vuln_url: str | None = None
    commit_fix_url: str | None = None
    summary: str | None = None
    cvss_score: float | None = None
    severity: str | None = None
    published_at: str | None = None
    updated_at: str | None = None
    vuln_code: str | None = None
    fixed_code: str | None = None
    trainable: bool = False
    has_code_pair: bool = False
    quality: dict[str, Any] | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_fce_input(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        payload = dict(data)

        payload["id"] = _clean_optional_text(payload.get("id"))
        payload["source"] = _clean_optional_text(payload.get("source"))
        payload["repo"] = _clean_optional_text(payload.get("repo"))
        payload["repo_url"] = _clean_optional_text(payload.get("repo_url"))
        payload["file_path"] = _clean_optional_text(payload.get("file_path"))
        payload["summary"] = _clean_optional_text(payload.get("summary"))
        payload["cve_id"] = _clean_optional_text(payload.get("cve_id"))
        payload["cwe_id"] = _clean_optional_text(payload.get("cwe_id"))
        payload["published_at"] = _clean_optional_text(payload.get("published_at"))
        payload["updated_at"] = _clean_optional_text(payload.get("updated_at"))
        payload["vuln_code"] = _clean_optional_text(payload.get("vuln_code"))
        payload["fixed_code"] = _clean_optional_text(payload.get("fixed_code"))

        commit_vuln = _clean_optional_text(payload.get("commit_vuln"))
        commit_fix = _clean_optional_text(payload.get("commit_fix") or payload.get("commit_fixed"))
        payload["commit_vuln"] = commit_vuln
        payload["commit_fix"] = commit_fix

        language = _clean_optional_text(payload.get("language"))
        payload["language"] = language.lower() if language else None

        severity = _clean_optional_text(payload.get("severity"))
        payload["severity"] = severity.upper() if severity else None

        if payload.get("cvss_score") is None and payload.get("score") is not None:
            payload["cvss_score"] = payload.get("score")
        payload.pop("score", None)

        osv_id = _clean_optional_text(payload.get("osv_id"))
        payload["osv_id"] = osv_id or _derive_osv_id(payload.get("id"))

        payload["commit_vuln_url"] = _clean_optional_text(
            payload.get("commit_vuln_url")
        ) or _derive_commit_url(payload.get("repo_url"), commit_vuln)
        payload["commit_fix_url"] = _clean_optional_text(
            payload.get("commit_fix_url")
        ) or _derive_commit_url(payload.get("repo_url"), commit_fix)

        has_code_pair = bool(payload.get("vuln_code")) and bool(payload.get("fixed_code"))
        payload["has_code_pair"] = (
            bool(payload.get("has_code_pair", has_code_pair)) or has_code_pair
        )

        if payload.get("source") is None:
            payload["source"] = "vuln_triage"

        payload.pop("commit_fixed", None)

        return payload
