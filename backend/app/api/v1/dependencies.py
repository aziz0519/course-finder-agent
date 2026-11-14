"""FastAPI dependencies that derive authorization from verified identity."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from app.api.v1.services import ApiServices
from app.auth.local_adapter import Principal
from app.domain.errors import UnknownStudentError
from app.domain.models import Student

SESSION_COOKIE = "course_finder_session"


def get_services(request: Request) -> ApiServices:
    return request.app.state.services


ServicesDep = Annotated[ApiServices, Depends(get_services)]


def get_principal(request: Request, services: ServicesDep) -> Principal:
    if services.settings.auth_provider != "local":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Configured authentication provider is not available in this build.",
        )
    principal = services.auth.authenticate(request.cookies.get(SESSION_COOKIE))
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return principal


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def require_csrf(
    request: Request,
    services: ServicesDep,
    principal: PrincipalDep,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> Principal:
    del principal
    if not services.auth.verify_csrf(
        request.cookies.get(SESSION_COOKIE),
        x_csrf_token,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Valid CSRF token required.",
        )
    authenticated = services.auth.authenticate(request.cookies.get(SESSION_COOKIE))
    if authenticated is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return authenticated


CsrfPrincipalDep = Annotated[Principal, Depends(require_csrf)]


def require_student(principal: PrincipalDep, services: ServicesDep) -> Student:
    if principal.role != "student" or not principal.student_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student role required.",
        )
    try:
        return services.dataset().student(principal.student_id)
    except UnknownStudentError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student record not found.",
        ) from exc


StudentDep = Annotated[Student, Depends(require_student)]


def require_admin(principal: PrincipalDep) -> Principal:
    if principal.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required.",
        )
    return principal


AdminDep = Annotated[Principal, Depends(require_admin)]


def require_csrf_admin(principal: CsrfPrincipalDep) -> Principal:
    if principal.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required.",
        )
    return principal


CsrfAdminDep = Annotated[Principal, Depends(require_csrf_admin)]
