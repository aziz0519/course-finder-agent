"""Authenticated catalogue routes over the authoritative fixture."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.api.v1.dependencies import PrincipalDep, ServicesDep
from app.domain.models import Course
from app.schemas.course import CourseResponse, CourseSearchResponse

router = APIRouter(prefix="/courses", tags=["courses"])


def course_response(course: Course) -> CourseResponse:
    return CourseResponse(
        course_id=course.course_id,
        course_code=course.course_code,
        title=course.title,
        units=course.units,
        description=course.description,
        prerequisite_course_ids=course.prerequisite_course_ids,
        terms_offered=tuple(sorted(str(season) for season in course.terms_offered)),
        reading_document_ids=course.reading_document_ids,
    )


@router.get("", response_model=CourseSearchResponse)
def search_courses(
    principal: PrincipalDep,
    services: ServicesDep,
    query: str | None = Query(default=None, max_length=100),
    season: str | None = Query(default=None, pattern="^(Fall|Spring)$"),
) -> CourseSearchResponse:
    del principal
    courses = services.dataset().catalog.courses
    if query:
        normalized = query.casefold()
        courses = tuple(
            course
            for course in courses
            if normalized in course.course_code.casefold()
            or normalized in course.title.casefold()
        )
    if season:
        courses = tuple(course for course in courses if course.offered_in(season))
    return CourseSearchResponse(
        total=len(courses),
        courses=tuple(course_response(course) for course in courses),
    )


@router.get("/{course_id}", response_model=CourseResponse)
def get_course(
    course_id: str,
    principal: PrincipalDep,
    services: ServicesDep,
) -> CourseResponse:
    del principal
    catalog = services.dataset().catalog
    course = catalog.maybe_course(course_id)
    if course is None:
        course = catalog.maybe_course(course_id.upper())
    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found.",
        )
    return course_response(course)
