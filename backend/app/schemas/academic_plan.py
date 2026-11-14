"""Academic-plan API contracts."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.agents.models import PlanningPayload


class PlanQuery(BaseModel):
    term: str = "Spring 2027"
    unit_cap: int | None = Field(default=None, gt=0)
    student_id: str | None = None


class PlanResponse(BaseModel):
    student_id: str
    plan: PlanningPayload
    disclaimer: str
