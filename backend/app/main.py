"""FastAPI application entry point for the M4 HTTP surface."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.routes import api_router
from app.api.v1.services import ApiServices
from app.core.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or get_settings()
    configured.assert_production_ready()
    application = FastAPI(
        title="Course Finder Agent API",
        version="0.4.0",
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
        openapi_url="/api/v1/openapi.json",
    )
    application.state.services = ApiServices.create(configured)
    origins = (
        ["http://localhost:3000", "http://127.0.0.1:3000"]
        if configured.app_env != "production"
        else []
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
    )
    application.include_router(api_router, prefix="/api/v1")

    @application.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logging.getLogger("app").exception(
            "Unhandled request error",
            extra={"path": request.url.path, "error_type": type(exc).__name__},
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "An unexpected error occurred."},
        )

    return application


app = create_app()
