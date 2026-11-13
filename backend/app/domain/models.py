"""Canonical domain models.

These are the typed objects the rest of the application reasons about. They are
deliberately independent of FastAPI, SQLAlchemy, agent runtimes, and model providers.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.terms import SeasonField, Term, TermField


class DomainModel(BaseModel):
    """Frozen, typo-intolerant base for canonical objects."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class CourseStatus(StrEnum):
    COMPLETED = "completed"
    IN_PROGRESS = "in_progress"


class RuleType(StrEnum):
    ALL = "all"
    CHOOSE = "choose"


class Course(DomainModel):
    """A catalogue course. ``course_id`` equals ``course_code`` for this dataset."""

    course_id: str = Field(min_length=1)
    course_code: str = Field(min_length=1)
    title: str = Field(min_length=1)
    units: int = Field(gt=0)
    description: str | None = None
    prerequisite_course_ids: tuple[str, ...] = ()
    terms_offered: frozenset[SeasonField]
    reading_document_ids: tuple[str, ...] = ()

    def offered_in(self, season: str) -> bool:
        return season in self.terms_offered


class RequirementGroup(DomainModel):
    """One degree requirement: every listed course, or ``count`` of them."""

    group_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    rule_type: RuleType
    required_course_ids: tuple[str, ...] = Field(min_length=1)
    count: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _count_matches_rule(self) -> RequirementGroup:
        if self.rule_type is RuleType.CHOOSE:
            if self.count is None:
                raise ValueError(f"choose-rule group {self.group_id!r} must declare count")
            if self.count > len(self.required_course_ids):
                raise ValueError(
                    f"choose-rule group {self.group_id!r} needs {self.count} of "
                    f"{len(self.required_course_ids)} listed courses"
                )
        elif self.count is not None:
            raise ValueError(f"all-rule group {self.group_id!r} must not declare count")
        return self

    @property
    def required_count(self) -> int:
        if self.rule_type is RuleType.ALL:
            return len(self.required_course_ids)
        if self.count is None:
            # Unreachable for a validated group; fail loudly rather than defaulting.
            raise ValueError(f"choose-rule group {self.group_id!r} has no count")
        return self.count

    def __contains__(self, course_id: object) -> bool:
        return course_id in self.required_course_ids


class Program(DomainModel):
    program_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    requirement_groups: tuple[RequirementGroup, ...] = Field(min_length=1)


class InProgressPrerequisitePolicy(DomainModel):
    """The typed form of the catalogue's in-progress prerequisite statement.

    ``allowed`` is only ever true when the source states the rule. An absent or
    unrecognised statement leaves it false, because guessing would silently grant
    prerequisite credit that no rule supports.
    """

    allowed: bool
    source_statement: str | None = None


class AcademicPolicy(DomainModel):
    current_term: TermField
    next_term: TermField
    max_units_per_term: int = Field(gt=0)
    in_progress_prerequisites: InProgressPrerequisitePolicy

    @model_validator(mode="after")
    def _terms_are_ordered(self) -> AcademicPolicy:
        if self.next_term <= self.current_term:
            raise ValueError(
                f"next_term ({self.next_term.label}) must be after "
                f"current_term ({self.current_term.label})"
            )
        return self

    def effective_unit_cap(self, requested: int | None = None) -> int:
        """Return ``min(catalogue maximum, request cap)`` without mutating policy."""
        if requested is None:
            return self.max_units_per_term
        if requested <= 0:
            raise ValueError(f"requested unit cap must be positive, got {requested}")
        return min(self.max_units_per_term, requested)

    def allows_in_progress_prerequisites_for(self, target_term: Term) -> bool:
        """In-progress coursework counts for the next term only, and only if stated."""
        return self.in_progress_prerequisites.allowed and target_term == self.next_term


class CourseRecord(DomainModel):
    """A course the student has taken or is taking, with its term and status."""

    course_id: str = Field(min_length=1)
    term: TermField
    status: CourseStatus


class Student(DomainModel):
    student_id: str = Field(min_length=1)
    academic_level: str = Field(min_length=1)
    program_id: str = Field(min_length=1)
    adviser_id: str = Field(min_length=1)
    completed_courses: tuple[CourseRecord, ...] = ()
    current_courses: tuple[CourseRecord, ...] = ()

    @model_validator(mode="after")
    def _statuses_are_consistent(self) -> Student:
        completed_ids = [record.course_id for record in self.completed_courses]
        current_ids = [record.course_id for record in self.current_courses]

        if len(set(completed_ids)) != len(completed_ids):
            raise ValueError(f"{self.student_id}: duplicate completed course record")
        if len(set(current_ids)) != len(current_ids):
            raise ValueError(f"{self.student_id}: duplicate current course record")
        overlap = set(completed_ids) & set(current_ids)
        if overlap:
            raise ValueError(
                f"{self.student_id}: course(s) both completed and in progress: "
                f"{', '.join(sorted(overlap))}"
            )
        for record in self.completed_courses:
            if record.status is not CourseStatus.COMPLETED:
                raise ValueError(
                    f"{self.student_id}: {record.course_id} in completed_courses "
                    f"must have status 'completed'"
                )
        for record in self.current_courses:
            if record.status is not CourseStatus.IN_PROGRESS:
                raise ValueError(
                    f"{self.student_id}: {record.course_id} in current_courses "
                    f"must have status 'in_progress'"
                )
        return self

    @property
    def completed_course_ids(self) -> tuple[str, ...]:
        return tuple(record.course_id for record in self.completed_courses)

    @property
    def current_course_ids(self) -> tuple[str, ...]:
        return tuple(record.course_id for record in self.current_courses)

    def completed_record(self, course_id: str) -> CourseRecord | None:
        return next(
            (record for record in self.completed_courses if record.course_id == course_id),
            None,
        )

    def current_record(self, course_id: str) -> CourseRecord | None:
        return next(
            (record for record in self.current_courses if record.course_id == course_id),
            None,
        )

    def is_completed(self, course_id: str) -> bool:
        return self.completed_record(course_id) is not None

    def is_current(self, course_id: str) -> bool:
        return self.current_record(course_id) is not None


class ReadingDocument(DomainModel):
    """A catalogue-referenced reading. Content fields are populated during ingestion."""

    document_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_filename: str = Field(min_length=1)
    week: int | None = Field(default=None, ge=1)
    file_checksum: str | None = None
    page_count: int | None = Field(default=None, ge=1)
    ingestion_version: str | None = None
