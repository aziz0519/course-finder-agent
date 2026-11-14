"""Adviser routes with assignment checks enforced server-side."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.v1.dependencies import PrincipalDep, ServicesDep
from app.api.v1.routes.students import degree_progress, student_profile
from app.domain.errors import UnknownStudentError
from app.schemas.student import AdviserStudentResponse

router = APIRouter(prefix="/advisers", tags=["advisers"])


@router.get("/students/{student_id}", response_model=AdviserStudentResponse)
def get_assigned_student(
    student_id: str,
    principal: PrincipalDep,
    services: ServicesDep,
) -> AdviserStudentResponse:
    if principal.role != "adviser" or not principal.adviser_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Adviser role required.",
        )
    try:
        student = services.dataset().student(student_id)
    except UnknownStudentError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    if student.adviser_id != principal.adviser_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student is not assigned to this adviser.",
        )
    return AdviserStudentResponse(
        student=student_profile(student),
        progress=degree_progress(student, services),
    )
