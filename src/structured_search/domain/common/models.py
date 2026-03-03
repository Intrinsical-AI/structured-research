"""Task-shared domain primitives."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BaseJobEntry(BaseModel):
    """Shared fields for any job-like document representation."""

    title: str = Field(..., description="Job title")
    company: str = Field(..., description="Company name")
    stack: list[str] = Field(default_factory=list, description="Technology stack")
    seniority: str | None = Field(None, description="Seniority level label")
    modality: str | None = Field(None, description="Work modality label")
    location: str | None = Field(None, description="Location string")
    description: str | None = Field(None, description="Description text")
    url: str | None = Field(None, description="Source URL")
