"""Student self-service routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.dependencies import PrincipalDep, ServicesDep, StudentDep
from app.domain.degree_progress import calculate_degree_progress
from app.domain.models import Student
from app.schemas.materials import (
    CourseMaterialResponse,
    ReadingMaterialResponse,
    StudentMaterialsResponse,
)
from app.schemas.student import (
    CourseRecordResponse,
    DegreeProgressResponse,
    RequirementProgressResponse,
    StudentProfile,
)

router = APIRouter(prefix="/students", tags=["students"])


def student_profile(student: Student) -> StudentProfile:
    def record(item) -> CourseRecordResponse:
        return CourseRecordResponse(
            course_code=item.course_id,
            term=item.term.label,
            status=item.status.value,
        )

    return StudentProfile(
        student_id=student.student_id,
        academic_level=student.academic_level,
        program_id=student.program_id,
        adviser_id=student.adviser_id,
        completed_courses=tuple(record(item) for item in student.completed_courses),
        current_courses=tuple(record(item) for item in student.current_courses),
    )


def degree_progress(student: Student, services: ServicesDep) -> DegreeProgressResponse:
    progress = calculate_degree_progress(student, services.dataset().catalog)
    return DegreeProgressResponse(
        student_id=student.student_id,
        program_id=progress.program.program_id,
        state=progress.state.value,
        requirement_groups=tuple(
            RequirementProgressResponse(
                group_id=group.group_id,
                label=group.label,
                state=group.state.value,
                required_count=group.required_count,
                completed_members=group.completed_members,
                in_progress_members=group.in_progress_members,
                remaining_options=group.remaining_options,
                courses_short=group.courses_short,
            )
            for group in progress.groups
        ),
    )


@router.get("/me", response_model=StudentProfile)
def get_own_profile(student: StudentDep) -> StudentProfile:
    return student_profile(student)


@router.get("/me/progress", response_model=DegreeProgressResponse)
def get_own_progress(student: StudentDep, services: ServicesDep) -> DegreeProgressResponse:
    return degree_progress(student, services)


@router.get("/me/materials", response_model=StudentMaterialsResponse)
def get_own_materials(
    student: StudentDep,
    principal: PrincipalDep,
    services: ServicesDep,
) -> StudentMaterialsResponse:
    """Current-term readings with ingestion and review state, never passage text."""

    dataset = services.dataset()
    scope = services.reading_scope(principal.user_id, student.student_id)
    active = {item.document_id: item for item in services.retriever.documents(scope)}
    courses = tuple(
        CourseMaterialResponse(
            course_code=record.course_id,
            title=course.title,
            units=course.units,
            term=record.term.label,
            readings=tuple(
                ReadingMaterialResponse(
                    document_id=document.document_id,
                    title=document.title,
                    page_count=(
                        active[document.document_id].page_count
                        if document.document_id in active
                        else document.page_count
                    ),
                    ingestion_version=(
                        active[document.document_id].ingestion_version
                        if document.document_id in active
                        else None
                    ),
                    ingested=document.document_id in active,
                    approved_assets=(
                        active[document.document_id].approved_assets
                        if document.document_id in active
                        else 0
                    ),
                    total_assets=(
                        active[document.document_id].total_assets
                        if document.document_id in active
                        else 0
                    ),
                    week=document.week,
                )
                for document in dataset.catalog.reading_documents
                if document.course_id == record.course_id
            ),
        )
        for record in student.current_courses
        for course in (dataset.catalog.course(record.course_id),)
    )
    return StudentMaterialsResponse(student_id=student.student_id, courses=courses)
