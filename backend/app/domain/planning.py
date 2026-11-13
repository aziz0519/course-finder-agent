"""Deterministic schedule proposal for a target term.

The unit cap is a maximum, not a target: the proposal only fills capacity with courses
that advance an unmet requirement. Everything else is reported as an alternative.

Coverage rule: if an ``all`` group course is neither completed nor in progress, it is
needed. If a ``choose`` group still has a shortfall once completed and in-progress
members are counted, eligible candidates fill that shortfall only. A group already met
by in-progress coursework produces no recommendation, which is why an in-progress
ENGL 120 does not trigger a redundant ENGL 130 suggestion.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.catalog import AcademicCatalog
from app.domain.eligibility import Eligibility, eligible_courses
from app.domain.models import AcademicPolicy, RuleType, Student
from app.domain.terms import Term


@dataclass(frozen=True)
class ScheduleProposal:
    target_term: Term
    catalogue_max_units: int
    unit_cap: int
    requested_unit_cap: int | None
    candidates: tuple[Eligibility, ...]
    recommended: tuple[Eligibility, ...]
    deferred: tuple[Eligibility, ...]
    alternatives: tuple[Eligibility, ...]

    @property
    def total_units(self) -> int:
        return sum(entry.course.units for entry in self.recommended)

    @property
    def recommended_course_ids(self) -> tuple[str, ...]:
        return tuple(entry.course_id for entry in self.recommended)

    @property
    def deferred_course_ids(self) -> tuple[str, ...]:
        return tuple(entry.course_id for entry in self.deferred)

    @property
    def alternative_course_ids(self) -> tuple[str, ...]:
        return tuple(entry.course_id for entry in self.alternatives)

    @property
    def is_capped(self) -> bool:
        return bool(self.deferred)


def _needed_courses(
    student: Student,
    catalog: AcademicCatalog,
    eligible_by_id: dict[str, Eligibility],
) -> list[Eligibility]:
    """Eligible courses that advance an unmet requirement, in importance order."""
    program = catalog.program(student.program_id)
    needed: list[Eligibility] = []
    seen: set[str] = set()

    for group in program.requirement_groups:
        covered = {
            member
            for member in group.required_course_ids
            if student.is_completed(member) or student.is_current(member)
        }

        if group.rule_type is RuleType.ALL:
            for member in group.required_course_ids:
                if member in covered or member in seen:
                    continue
                candidate = eligible_by_id.get(member)
                if candidate is not None:
                    needed.append(candidate)
                    seen.add(member)
            continue

        shortfall = group.required_count - len(covered)
        if shortfall <= 0:
            continue
        candidates = sorted(
            (
                eligible_by_id[member]
                for member in group.required_course_ids
                if member in eligible_by_id and member not in covered
            ),
            key=lambda entry: entry.rank_key,
        )
        for candidate in candidates[:shortfall]:
            if candidate.course_id in seen:
                continue
            needed.append(candidate)
            seen.add(candidate.course_id)

    return sorted(needed, key=lambda entry: entry.rank_key)


def propose_schedule(
    student: Student,
    catalog: AcademicCatalog,
    *,
    target_term: Term | None = None,
    requested_unit_cap: int | None = None,
    policy: AcademicPolicy | None = None,
) -> ScheduleProposal:
    """Propose a capped schedule. Never exceeds ``min(catalogue max, request cap)``."""
    active_policy = policy or catalog.policy
    term = target_term or active_policy.next_term
    unit_cap = active_policy.effective_unit_cap(requested_unit_cap)

    candidates = eligible_courses(student, catalog, term, policy=active_policy)
    eligible_by_id = {entry.course_id: entry for entry in candidates}

    needed = _needed_courses(student, catalog, eligible_by_id)

    recommended: list[Eligibility] = []
    deferred: list[Eligibility] = []
    total_units = 0

    for entry in needed:
        if total_units + entry.course.units <= unit_cap:
            recommended.append(entry)
            total_units += entry.course.units
        else:
            deferred.append(entry)

    chosen = {entry.course_id for entry in recommended} | {entry.course_id for entry in deferred}
    alternatives = tuple(entry for entry in candidates if entry.course_id not in chosen)

    return ScheduleProposal(
        target_term=term,
        catalogue_max_units=active_policy.max_units_per_term,
        unit_cap=unit_cap,
        requested_unit_cap=requested_unit_cap,
        candidates=candidates,
        recommended=tuple(recommended),
        deferred=tuple(deferred),
        alternatives=alternatives,
    )
