"""Aggregate all version-1 API routes."""

from fastapi import APIRouter

from .academic_plan import router as academic_plan_router
from .admin_ingest import router as admin_ingest_router
from .advisers import router as advisers_router
from .auth import router as auth_router
from .chat import router as chat_router
from .courses import router as courses_router
from .students import router as students_router

api_router = APIRouter()

# Mount all sub-routers
api_router.include_router(auth_router)
api_router.include_router(students_router)
api_router.include_router(advisers_router)
api_router.include_router(courses_router)
api_router.include_router(chat_router)
api_router.include_router(academic_plan_router)
api_router.include_router(admin_ingest_router)
