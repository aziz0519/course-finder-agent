"""Deterministic academic-plan endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.agents.academic_planner import plan
from app.api.v1.dependencies import PrincipalDep, ServicesDep
from app.domain.errors import UnknownStudentError
from app.domain.models import Student
from app.schemas.academic_plan import PlanQuery, PlanResponse

router = APIRouter(prefix="/academic-plan", tags=["academic-plan"])


def _authorized_student(
    query: PlanQuery,
    principal: PrincipalDep,
    services: ServicesDep,
) -> Student:
    student_id = query.student_id or principal.student_id
    if not student_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="student_id is required for adviser requests.",
        )
    try:
        student = services.dataset().student(student_id)
    except UnknownStudentError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    own_record = principal.role == "student" and principal.student_id == student_id
    assigned = principal.role == "adviser" and principal.adviser_id == student.adviser_id
    if not own_record and not assigned:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student record unavailable.",
        )
    return student


@router.get("", response_model=PlanResponse)
def get_academic_plan(
    query: Annotated[PlanQuery, Depends()],
    principal: PrincipalDep,
    services: ServicesDep,
) -> PlanResponse:
    dataset = services.dataset()
    if query.term != dataset.catalog.policy.next_term.label:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Only {dataset.catalog.policy.next_term.label} is supported by this snapshot.",
        )
    student = _authorized_student(query, principal, services)
    response = plan(
        student,
        dataset.catalog,
        unit_cap=query.unit_cap,
        catalogue_version=dataset.catalogue_source.source_version,
        student_record_version=dataset.students_source.source_version,
    )
    if response.planning is None:
        raise RuntimeError("planner returned no structured plan")
    return PlanResponse(
        student_id=student.student_id,
        plan=response.planning,
        disclaimer=(
            "Suggested candidates from the supplied snapshot; this is not an official "
            "study plan or a guarantee of seats or timetable compatibility."
        ),
    )
