"""Student and degree-progress API contracts."""

from __future__ import annotations

from pydantic import BaseModel


class CourseRecordResponse(BaseModel):
    course_code: str
    term: str
    status: str


class StudentProfile(BaseModel):
    student_id: str
    academic_level: str
    program_id: str
    adviser_id: str
    completed_courses: tuple[CourseRecordResponse, ...]
    current_courses: tuple[CourseRecordResponse, ...]


class RequirementProgressResponse(BaseModel):
    group_id: str
    label: str
    state: str
    required_count: int
    completed_members: tuple[str, ...]
    in_progress_members: tuple[str, ...]
    remaining_options: tuple[str, ...]
    courses_short: int


class DegreeProgressResponse(BaseModel):
    student_id: str
    program_id: str
    state: str
    requirement_groups: tuple[RequirementProgressResponse, ...]


class AdviserStudentResponse(BaseModel):
    student: StudentProfile
    progress: DegreeProgressResponse
