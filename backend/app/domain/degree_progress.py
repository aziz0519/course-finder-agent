"""Deterministic degree-progress evaluation.

Current enrolment is reported as ``in_progress`` and never as completed credit. Only a
completed-course record can satisfy a requirement.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain.catalog import AcademicCatalog
from app.domain.models import Program, RequirementGroup, RuleType, Student


class RequirementState(StrEnum):
    SATISFIED = "satisfied"
    IN_PROGRESS = "in_progress"
    REMAINING = "remaining"
    UNABLE_TO_DETERMINE = "unable_to_determine"


@dataclass(frozen=True)
class RequirementGroupProgress:
    group: RequirementGroup
    state: RequirementState
    required_count: int
    completed_members: tuple[str, ...]
    in_progress_members: tuple[str, ...]
    remaining_options: tuple[str, ...]
    courses_short: int
    notes: tuple[str, ...] = ()

    @property
    def group_id(self) -> str:
        return self.group.group_id

    @property
    def label(self) -> str:
        return self.group.label

    @property
    def satisfied_by(self) -> tuple[str, ...]:
        """The completed courses that count toward the requirement."""
        return self.completed_members[: self.required_count]


@dataclass(frozen=True)
class DegreeProgress:
    program: Program
    groups: tuple[RequirementGroupProgress, ...]

    @property
    def state(self) -> RequirementState:
        states = {group.state for group in self.groups}
        if RequirementState.UNABLE_TO_DETERMINE in states:
            return RequirementState.UNABLE_TO_DETERMINE
        if states == {RequirementState.SATISFIED}:
            return RequirementState.SATISFIED
        if RequirementState.IN_PROGRESS in states:
            return RequirementState.IN_PROGRESS
        return RequirementState.REMAINING

    def group(self, group_id: str) -> RequirementGroupProgress:
        for progress in self.groups:
            if progress.group_id == group_id:
                return progress
        raise KeyError(group_id)

    @property
    def satisfied_group_ids(self) -> tuple[str, ...]:
        return tuple(
            group.group_id for group in self.groups if group.state is RequirementState.SATISFIED
        )


def _evaluate_all_group(
    group: RequirementGroup,
    student: Student,
    catalog: AcademicCatalog,
) -> RequirementGroupProgress:
    members = group.required_course_ids
    unknown = tuple(member for member in members if catalog.maybe_course(member) is None)

    completed = tuple(member for member in members if student.is_completed(member))
    in_progress = tuple(member for member in members if student.is_current(member))
    covered = set(completed) | set(in_progress)
    short = max(0, len(members) - len(covered))

    if unknown:
        return RequirementGroupProgress(
            group=group,
            state=RequirementState.UNABLE_TO_DETERMINE,
            required_count=len(members),
            completed_members=completed,
            in_progress_members=in_progress,
            remaining_options=(),
            courses_short=short,
            notes=(f"unknown catalogue course(s): {', '.join(unknown)}",),
        )

    if len(completed) == len(members):
        state = RequirementState.SATISFIED
    elif short == 0:
        state = RequirementState.IN_PROGRESS
    else:
        state = RequirementState.REMAINING

    return RequirementGroupProgress(
        group=group,
        state=state,
        required_count=len(members),
        completed_members=completed,
        in_progress_members=in_progress,
        remaining_options=tuple(
            member for member in members if member not in completed and member not in in_progress
        ),
        courses_short=short,
    )


def _evaluate_choose_group(
    group: RequirementGroup,
    student: Student,
    catalog: AcademicCatalog,
) -> RequirementGroupProgress:
    members = group.required_course_ids
    required_count = group.required_count
    unknown = tuple(member for member in members if catalog.maybe_course(member) is None)

    completed = tuple(member for member in members if student.is_completed(member))
    in_progress = tuple(member for member in members if student.is_current(member))
    covered_count = len(completed) + len(in_progress)
    short = max(0, required_count - covered_count)

    if unknown:
        return RequirementGroupProgress(
            group=group,
            state=RequirementState.UNABLE_TO_DETERMINE,
            required_count=required_count,
            completed_members=completed,
            in_progress_members=in_progress,
            remaining_options=(),
            courses_short=short,
            notes=(f"unknown catalogue course(s): {', '.join(unknown)}",),
        )

    if len(completed) >= required_count:
        state = RequirementState.SATISFIED
    elif covered_count >= required_count:
        state = RequirementState.IN_PROGRESS
    else:
        state = RequirementState.REMAINING

    return RequirementGroupProgress(
        group=group,
        state=state,
        required_count=required_count,
        completed_members=completed,
        in_progress_members=in_progress,
        remaining_options=tuple(
            member for member in members if member not in completed and member not in in_progress
        ),
        courses_short=short,
    )


def calculate_degree_progress(student: Student, catalog: AcademicCatalog) -> DegreeProgress:
    """Evaluate every requirement group of the student's programme."""
    program = catalog.program(student.program_id)
    groups = tuple(
        _evaluate_all_group(group, student, catalog)
        if group.rule_type is RuleType.ALL
        else _evaluate_choose_group(group, student, catalog)
        for group in program.requirement_groups
    )
    return DegreeProgress(program=program, groups=groups)
