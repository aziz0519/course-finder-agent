"""Course catalogue API contracts."""

from __future__ import annotations

from pydantic import BaseModel


class CourseResponse(BaseModel):
    course_id: str
    course_code: str
    title: str
    units: int
    description: str | None
    prerequisite_course_ids: tuple[str, ...]
    terms_offered: tuple[str, ...]
    reading_document_ids: tuple[str, ...]


class CourseSearchResponse(BaseModel):
    total: int
    courses: tuple[CourseResponse, ...]
