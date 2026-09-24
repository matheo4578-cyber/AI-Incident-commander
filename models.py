from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

Severity = Literal["low", "medium", "high", "critical"]


class IncidentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5000)
    logs: list[str] = Field(default_factory=list, max_length=100)
    metrics: dict[str, float] = Field(default_factory=dict, max_length=100)

    @field_validator("service", "title", "description")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("logs")
    @classmethod
    def clean_logs(cls, values: list[str]) -> list[str]:
        return [value.strip()[:2000] for value in values if value.strip()]


class IncidentInput(IncidentRequest):
    incident_id: str = Field(
        default_factory=lambda: f"inc-{uuid4().hex[:12]}",
        pattern=r"^inc-[a-zA-Z0-9-]{3,64}$",
    )
    source: str = Field(default="manual", min_length=1, max_length=50)

    @field_validator("source")
    @classmethod
    def strip_source(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value


class IncidentReport(BaseModel):
    incident_id: str
    service: str
    status: Literal["completed", "failed"]
    severity: Severity
    summary: str
    probable_root_cause: str
    confidence: float = Field(ge=0, le=1)
    evidence: list[str]
    recommendations: list[str]
    timeline: list[str]
    agents_run: list[str]
    requires_human_approval: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
