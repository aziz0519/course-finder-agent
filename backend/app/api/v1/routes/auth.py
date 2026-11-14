"""Local authentication routes; Cognito remains a production adapter seam."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.v1.dependencies import (
    SESSION_COOKIE,
    CsrfPrincipalDep,
    PrincipalDep,
    ServicesDep,
)
from app.auth.local_adapter import LoginRateLimitedError
from app.schemas.auth import LoginRequest, LoginResponse, LogoutResponse, MeResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    services: ServicesDep,
) -> LoginResponse:
    if services.settings.auth_provider != "local":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Local login is disabled.",
        )
    client_key = request.client.host if request.client else "unknown"
    try:
        token, csrf, principal = services.auth.login(
            payload.username,
            payload.password,
            client_key,
        )
    except LoginRateLimitedError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        ) from exc
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=services.settings.app_env == "production",
        samesite="lax",
        max_age=services.settings.session_ttl_seconds,
        path="/",
    )
    return LoginResponse(
        user_id=principal.user_id,
        role=principal.role,
        student_id=principal.student_id,
        adviser_id=principal.adviser_id,
        csrf_token=csrf,
    )


@router.get("/me", response_model=MeResponse)
def me(principal: PrincipalDep) -> MeResponse:
    return MeResponse(**principal.model_dump())


@router.post("/logout", response_model=LogoutResponse)
def logout(
    request: Request,
    response: Response,
    services: ServicesDep,
    principal: CsrfPrincipalDep,
) -> LogoutResponse:
    del principal
    services.auth.logout(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/")
    return LogoutResponse()


@router.get("/callback", include_in_schema=False)
def oidc_callback() -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Cognito callback is not configured.",
    )
