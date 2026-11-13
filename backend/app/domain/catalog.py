"""The academic catalogue aggregate.

Holds the catalogue, degree requirements, and policy together, precomputes the lookups
the eligibility and degree engines need, and validates referential integrity on
construction so any construction path fails closed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.errors import DatasetError, UnknownCourseError, UnknownProgramError
from app.domain.models import AcademicPolicy, Course, Program, ReadingDocument, RequirementGroup


@dataclass
class AcademicCatalog:
    """Validated, indexed view of one catalogue source version."""

    policy: AcademicPolicy
    courses: tuple[Course, ...]
    programs: tuple[Program, ...]
    reading_documents: tuple[ReadingDocument, ...] = ()
    courses_by_id: dict[str, Course] = field(init=False, repr=False, default_factory=dict)
    programs_by_id: dict[str, Program] = field(init=False, repr=False, default_factory=dict)
    documents_by_id: dict[str, ReadingDocument] = field(
        init=False, repr=False, default_factory=dict
    )
    groups_by_id: dict[str, RequirementGroup] = field(init=False, repr=False, default_factory=dict)

    def __post_init__(self) -> None:
        self.courses_by_id = self._index_courses()
        self.programs_by_id = self._index_programs()
        self.documents_by_id = self._index_documents()
        self.groups_by_id = {
            group.group_id: group
            for program in self.programs
            for group in program.requirement_groups
        }
        self._check_references()

    # --- Indexing ---------------------------------------------------------------

    def _index_courses(self) -> dict[str, Course]:
        index: dict[str, Course] = {}
        for course in self.courses:
            if course.course_id in index:
                raise DatasetError(f"duplicate course id: {course.course_id!r}")
            index[course.course_id] = course
        if not index:
            raise DatasetError("catalogue contains no courses")
        return index

    def _index_programs(self) -> dict[str, Program]:
        index: dict[str, Program] = {}
        for program in self.programs:
            if program.program_id in index:
                raise DatasetError(f"duplicate programme id: {program.program_id!r}")
            index[program.program_id] = program
        if not index:
            raise DatasetError("catalogue contains no programmes")
        return index

    def _index_documents(self) -> dict[str, ReadingDocument]:
        index: dict[str, ReadingDocument] = {}
        for document in self.reading_documents:
            if document.document_id in index:
                raise DatasetError(f"duplicate reading document id: {document.document_id!r}")
            index[document.document_id] = document
        return index

    # --- Referential integrity ---------------------------------------------------

    def _check_references(self) -> None:
        for course in self.courses:
            for prerequisite_id in course.prerequisite_course_ids:
                if prerequisite_id not in self.courses_by_id:
                    raise DatasetError(
                        f"{course.course_code}: prerequisite {prerequisite_id!r} "
                        "is not in the catalogue"
                    )
                if prerequisite_id == course.course_id:
                    raise DatasetError(f"{course.course_code}: cannot require itself")

            for document_id in course.reading_document_ids:
                document = self.documents_by_id.get(document_id)
                if document is None:
                    raise DatasetError(f"{course.course_code}: reading {document_id!r} is missing")
                if document.course_id != course.course_id:
                    raise DatasetError(
                        f"{document_id}: document belongs to {document.course_id}, "
                        f"not {course.course_id}"
                    )

        for program in self.programs:
            seen_groups: set[str] = set()
            for group in program.requirement_groups:
                if group.group_id in seen_groups:
                    raise DatasetError(
                        f"{program.program_id}: duplicate requirement group {group.group_id!r}"
                    )
                seen_groups.add(group.group_id)
                for member_id in group.required_course_ids:
                    if member_id not in self.courses_by_id:
                        raise DatasetError(
                            f"{group.group_id}: course {member_id!r} is not in the catalogue"
                        )

        for document in self.reading_documents:
            if document.course_id not in self.courses_by_id:
                raise DatasetError(f"{document.document_id}: unknown course {document.course_id!r}")

    # --- Lookups -----------------------------------------------------------------

    def course(self, course_id: str) -> Course:
        try:
            return self.courses_by_id[course_id]
        except KeyError:
            raise UnknownCourseError(course_id) from None

    def maybe_course(self, course_id: str) -> Course | None:
        return self.courses_by_id.get(course_id)

    def program(self, program_id: str) -> Program:
        try:
            return self.programs_by_id[program_id]
        except KeyError:
            raise UnknownProgramError(program_id) from None

    def document(self, document_id: str) -> ReadingDocument | None:
        return self.documents_by_id.get(document_id)

    def groups_for_course(self, course_id: str) -> tuple[RequirementGroup, ...]:
        """All requirement groups that list ``course_id``, in catalogue order."""
        if course_id not in self.courses_by_id:
            raise UnknownCourseError(course_id)
        return tuple(
            group
            for program in self.programs
            for group in program.requirement_groups
            if course_id in group
        )

    def courses_in_group(self, group_id: str) -> tuple[Course, ...]:
        group = self.groups_by_id.get(group_id)
        if group is None:
            raise DatasetError(f"unknown requirement group: {group_id!r}")
        return tuple(self.course(course_id) for course_id in group.required_course_ids)

    @property
    def course_ids(self) -> tuple[str, ...]:
        return tuple(self.courses_by_id)
