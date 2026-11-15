"""Authorized course-reading metadata for the student materials view."""

from __future__ import annotations

from pydantic import BaseModel


class ReadingMaterialResponse(BaseModel):
    document_id: str
    title: str
    page_count: int | None = None
    ingestion_version: str | None = None
    ingested: bool
    approved_assets: int
    total_assets: int
    week: int | None = None


class CourseMaterialResponse(BaseModel):
    course_code: str
    title: str
    units: int
    term: str
    readings: tuple[ReadingMaterialResponse, ...]


class StudentMaterialsResponse(BaseModel):
    student_id: str
    courses: tuple[CourseMaterialResponse, ...]
