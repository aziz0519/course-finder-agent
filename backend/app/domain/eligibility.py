"""Deterministic prerequisite and term eligibility.

The rules implemented here are the only authority on whether a course may be
recommended. A language model may explain the output of this module; it may not
produce or override it.

Concurrency invariant: prerequisites are satisfied only by *completed* coursework and,
for the next term under an explicit catalogue policy, by *in-progress* coursework.
Courses being considered for the target term are never inputs here, so two Spring 2027
courses can never satisfy one another's prerequisites.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain.catalog import AcademicCatalog
from app.domain.models import (
    AcademicPolicy,
    Course,
    CourseStatus,
    RequirementGroup,
    RuleType,
    Student,
)
from app.domain.terms import Term


class IneligibilityReason(StrEnum):
    ALREADY_COMPLETED = "already_completed"
    CURRENTLY_IN_PROGRESS = "currently_in_progress"
    NOT_OFFERED_IN_TERM = "not_offered_in_term"
    PREREQUISITE_NOT_MET = "prerequisite_not_met"


@dataclass(frozen=True)
class PrerequisiteEvidence:
    """One satisfied prerequisite, with the record that satisfies it."""

    course_id: str
    status: CourseStatus
    term: Term

    @property
    def description(self) -> str:
        if self.status is CourseStatus.COMPLETED:
            return f"completed {self.term.label}"
        return f"in progress {self.term.label}"


@dataclass(frozen=True)
class PrerequisiteOutcome:
    satisfied: bool
    met: tuple[PrerequisiteEvidence, ...]
    missing: tuple[str, ...]
    in_progress_not_applicable: tuple[str, ...] = ()

    @property
    def in_progress_used(self) -> tuple[str, ...]:
        return tuple(
            evidence.course_id
            for evidence in self.met
            if evidence.status is CourseStatus.IN_PROGRESS
        )


@dataclass(frozen=True)
class Eligibility:
    """The full, auditable decision for one course and one target term."""

    course: Course
    target_term: Term
    eligible: bool
    reasons: tuple[IneligibilityReason, ...]
    prerequisite: PrerequisiteOutcome
    requirement_groups: tuple[str, ...]
    mandatory: bool
    unlock_score: int
    explanation: tuple[str, ...]

    @property
    def course_id(self) -> str:
        return self.course.course_id

    @property
    def priority(self) -> int:
        """0 = required by an ``all`` group, 1 = optional/choose coverage."""
        return 0 if self.mandatory else 1

    @property
    def rank_key(self) -> tuple[int, int, str]:
        return (self.priority, -self.unlock_score, self.course.course_code)


def _program_groups(catalog: AcademicCatalog, program_id: str) -> tuple[RequirementGroup, ...]:
    """Requirement groups of one programme.

    Another programme's rules must never affect this student's eligibility, priority,
    or requirement attribution, even when both programmes list the same course.
    """
    return catalog.program(program_id).requirement_groups


def _unlock_score(
    catalog: AcademicCatalog, program_id: str, course_id: str, student: Student
) -> int:
    """How many still-unmet programme courses list ``course_id`` as a prerequisite.

    A downstream course the student already completed or is taking no longer needs
    unlocking, so counting it would overstate this course's ranking value.
    """
    groups = _program_groups(catalog, program_id)
    return sum(
        1
        for other in catalog.courses
        if course_id in other.prerequisite_course_ids
        and any(other.course_id in group for group in groups)
        and not student.is_completed(other.course_id)
        and not student.is_current(other.course_id)
    )


def _requirement_context(
    catalog: AcademicCatalog, program_id: str, course_id: str
) -> tuple[tuple[str, ...], bool]:
    groups = tuple(group for group in _program_groups(catalog, program_id) if course_id in group)
    group_ids = tuple(group.group_id for group in groups)
    mandatory = any(group.rule_type is RuleType.ALL for group in groups)
    return group_ids, mandatory


def evaluate_prerequisites(
    course: Course,
    student: Student,
    catalog: AcademicCatalog,
    policy: AcademicPolicy,
    target_term: Term,
) -> PrerequisiteOutcome:
    """Check every prerequisite against completed coursework and (conditionally) in-progress."""
    use_in_progress = policy.allows_in_progress_prerequisites_for(target_term)

    met: list[PrerequisiteEvidence] = []
    missing: list[str] = []
    blocked_by_policy: list[str] = []

    for prerequisite_id in course.prerequisite_course_ids:
        # Fail closed: an unresolvable prerequisite is never treated as satisfied.
        catalog.course(prerequisite_id)

        completed = student.completed_record(prerequisite_id)
        if completed is not None:
            met.append(
                PrerequisiteEvidence(
                    course_id=prerequisite_id,
                    status=CourseStatus.COMPLETED,
                    term=completed.term,
                )
            )
            continue

        current = student.current_record(prerequisite_id)
        if current is not None and use_in_progress:
            met.append(
                PrerequisiteEvidence(
                    course_id=prerequisite_id,
                    status=CourseStatus.IN_PROGRESS,
                    term=current.term,
                )
            )
            continue

        if current is not None:
            blocked_by_policy.append(prerequisite_id)
        missing.append(prerequisite_id)

    return PrerequisiteOutcome(
        satisfied=not missing,
        met=tuple(met),
        missing=tuple(missing),
        in_progress_not_applicable=tuple(blocked_by_policy),
    )


def evaluate_course(
    course: Course,
    student: Student,
    catalog: AcademicCatalog,
    target_term: Term,
    *,
    policy: AcademicPolicy | None = None,
) -> Eligibility:
    """Evaluate one course for one student and target term."""
    active_policy = policy or catalog.policy
    reasons: list[IneligibilityReason] = []
    explanation: list[str] = []

    completed = student.completed_record(course.course_id)
    if completed is not None:
        reasons.append(IneligibilityReason.ALREADY_COMPLETED)
        explanation.append(f"{course.course_code} is already completed ({completed.term.label}).")

    current = student.current_record(course.course_id)
    if current is not None:
        reasons.append(IneligibilityReason.CURRENTLY_IN_PROGRESS)
        explanation.append(f"{course.course_code} is already in progress ({current.term.label}).")

    if not course.offered_in(target_term.season):
        reasons.append(IneligibilityReason.NOT_OFFERED_IN_TERM)
        seasons = ", ".join(sorted(course.terms_offered))
        explanation.append(
            f"{course.course_code} is not offered in {target_term.label} (offered: {seasons})."
        )

    prerequisites = evaluate_prerequisites(course, student, catalog, active_policy, target_term)
    if not prerequisites.satisfied:
        reasons.append(IneligibilityReason.PREREQUISITE_NOT_MET)
        missing = ", ".join(prerequisites.missing)
        explanation.append(
            f"{course.course_code} requires {missing}, which is not satisfied by "
            f"completed courses"
            + (
                f" or {active_policy.current_term.label} enrolments."
                if active_policy.allows_in_progress_prerequisites_for(target_term)
                else "."
            )
        )
        if prerequisites.in_progress_not_applicable:
            blocked = ", ".join(prerequisites.in_progress_not_applicable)
            explanation.append(
                f"{blocked} is in progress but counts only toward "
                f"{active_policy.next_term.label} prerequisites."
            )

    group_ids, mandatory = _requirement_context(catalog, student.program_id, course.course_id)
    unlock_score = _unlock_score(catalog, student.program_id, course.course_id, student)

    eligible = not reasons
    if eligible:
        for evidence in prerequisites.met:
            explanation.append(
                f"Prerequisite {evidence.course_id} satisfied by {evidence.description}."
            )
        if not course.prerequisite_course_ids:
            explanation.append(f"{course.course_code} has no prerequisites.")
        explanation.append(f"Offered in {target_term.label}.")
        if group_ids:
            explanation.append(f"Counts toward requirement group(s): {', '.join(group_ids)}.")

    return Eligibility(
        course=course,
        target_term=target_term,
        eligible=eligible,
        reasons=tuple(reasons),
        prerequisite=prerequisites,
        requirement_groups=group_ids,
        mandatory=mandatory,
        unlock_score=unlock_score,
        explanation=tuple(explanation),
    )


def evaluate_all(
    student: Student,
    catalog: AcademicCatalog,
    target_term: Term,
    *,
    policy: AcademicPolicy | None = None,
) -> tuple[Eligibility, ...]:
    """Evaluate every catalogue course, preserving catalogue order."""
    return tuple(
        evaluate_course(course, student, catalog, target_term, policy=policy)
        for course in catalog.courses
    )


def eligible_courses(
    student: Student,
    catalog: AcademicCatalog,
    target_term: Term,
    *,
    policy: AcademicPolicy | None = None,
) -> tuple[Eligibility, ...]:
    """Return eligible courses ordered by requirement priority, unlocks, then code."""
    decisions = evaluate_all(student, catalog, target_term, policy=policy)
    return tuple(sorted((d for d in decisions if d.eligible), key=lambda d: d.rank_key))
