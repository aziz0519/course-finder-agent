"""Domain errors.

Every one of these means "we cannot answer that safely", never "guess a default".
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for deterministic domain failures."""


class DatasetError(DomainError):
    """A supplied source file is structurally valid but academically inconsistent."""


class UnknownCourseError(DomainError):
    def __init__(self, course_id: str) -> None:
        super().__init__(f"unknown course: {course_id!r}")
        self.course_id = course_id


class UnknownProgramError(DomainError):
    def __init__(self, program_id: str) -> None:
        super().__init__(f"unknown programme: {program_id!r}")
        self.program_id = program_id


class UnknownStudentError(DomainError):
    def __init__(self, student_id: str) -> None:
        super().__init__(f"unknown student: {student_id!r}")
        self.student_id = student_id


class PolicyError(DomainError):
    """The catalogue does not state a rule we can execute without guessing."""
