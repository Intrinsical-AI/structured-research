"""Neutral shared task models.

These models are intentionally task-agnostic enough to be reused by
multiple task slices without creating cross-slice imports.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class BaseJobEntry(BaseModel):
    """Shared fields for any job-posting representation."""

    title: str = Field(..., description="Job title")
    company: str = Field(..., description="Company name")
    stack: list[str] = Field(default_factory=list, description="Technology stack")
    seniority: str | None = Field(None, description="Seniority level label")
    modality: str | None = Field(None, description="Work modality label (remote, hybrid, on_site)")
    location: str | None = Field(None, description="Location string")
    description: str | None = Field(None, description="Job description text")
    url: str | None = Field(None, description="Job posting URL")
