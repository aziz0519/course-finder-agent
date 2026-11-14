"""Typed contracts shared by the M3 supervisor and specialist agents."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.domain.models import DomainModel

Intent = Literal["tutor", "planner", "unsupported"]
ResponseStatus = Literal[
    "ok",
    "clarification_required",
    "insufficient_evidence",
    "unsupported",
]


class Citation(DomainModel):
    document_title: str
    document_id: str
    course_code: str
    pdf_page_number: int = Field(ge=1)
    chunk_id: str | None = None
    asset_id: str | None = None
    label: str | None = None


class PlanningCourse(DomainModel):
    course_id: str
    title: str
    units: int = Field(gt=0)
    explanations: tuple[str, ...]


class AcademicEvidence(DomainModel):
    source_type: Literal["catalogue", "student_record"]
    source_version: str = Field(min_length=1)
    description: str = Field(min_length=1)


class PlanningPayload(DomainModel):
    target_term: str
    catalogue_max_units: int = Field(gt=0)
    effective_unit_cap: int = Field(gt=0)
    requested_unit_cap: int | None = Field(default=None, gt=0)
    total_units: int = Field(ge=0)
    recommended: tuple[PlanningCourse, ...]
    deferred: tuple[PlanningCourse, ...]
    alternatives: tuple[PlanningCourse, ...]
    evidence: tuple[AcademicEvidence, ...]


class AgentResponse(DomainModel):
    status: ResponseStatus
    intent: Intent
    text: str
    citations: tuple[Citation, ...] = ()
    planning: PlanningPayload | None = None
    trace_ids: tuple[str, ...] = ()


class ConversationState(DomainModel):
    """Compact checkpoint. Academic facts and source excerpts are deliberately absent."""

    last_intent: Intent | None = None
    planning_unit_cap: int | None = Field(default=None, gt=0)
    active_course_id: str | None = None
    active_document_id: str | None = None
    candidate_asset_ids: tuple[str, ...] = ()
    last_asset_id: str | None = None
    pending_visual_exact: bool = False


class TraceEvent(DomainModel):
    """Redacted orchestration metadata; never prompts, passages, or chain-of-thought."""

    trace_id: str = Field(min_length=1)
    agent_name: Literal["supervisor", "tutor", "planner"]
    status: ResponseStatus
    metadata: dict[str, str] = Field(default_factory=dict)
