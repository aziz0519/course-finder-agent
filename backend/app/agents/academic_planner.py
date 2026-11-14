"""Planner specialist: explain, but never replace, deterministic domain results."""

from __future__ import annotations

import re

from app.agents.models import AgentResponse, PlanningCourse, PlanningPayload
from app.domain.catalog import AcademicCatalog
from app.domain.models import Student
from app.domain.planning import ScheduleProposal, propose_schedule

CAP = re.compile(r"\b(?:cap(?:\s+me)?\s+(?:at|to)?|keep\s+it\s+to)\s*(\d+)\s*units?\b", re.I)


def requested_unit_cap(message: str) -> int | None:
    match = CAP.search(message)
    return int(match.group(1)) if match else None


def _course(entry) -> PlanningCourse:
    return PlanningCourse(
        course_id=entry.course_id,
        title=entry.course.title,
        units=entry.course.units,
        explanations=entry.explanation,
    )


def _payload(proposal: ScheduleProposal) -> PlanningPayload:
    return PlanningPayload(
        target_term=proposal.target_term.label,
        catalogue_max_units=proposal.catalogue_max_units,
        effective_unit_cap=proposal.unit_cap,
        requested_unit_cap=proposal.requested_unit_cap,
        total_units=proposal.total_units,
        recommended=tuple(_course(entry) for entry in proposal.recommended),
        deferred=tuple(_course(entry) for entry in proposal.deferred),
        alternatives=tuple(_course(entry) for entry in proposal.alternatives),
    )


def plan(
    student: Student,
    catalog: AcademicCatalog,
    *,
    unit_cap: int | None,
) -> AgentResponse:
    proposal = propose_schedule(student, catalog, requested_unit_cap=unit_cap)
    courses = ", ".join(
        f"{entry.course.course_code} ({entry.course.units} units)"
        for entry in proposal.recommended
    )
    text = (
        f"Suggested {proposal.target_term.label} candidates: {courses or 'none'} "
        f"({proposal.total_units} units; effective cap {proposal.unit_cap})."
    )
    for entry in proposal.recommended:
        text += " " + " ".join(entry.explanation)
        for group_id in entry.requirement_groups:
            group = catalog.groups_by_id[group_id]
            in_progress_choices = tuple(
                course_id
                for course_id in group.required_course_ids
                if student.is_current(course_id)
            )
            if in_progress_choices and entry.course_id not in in_progress_choices:
                text += (
                    f" Its contribution to {group.label} assumes successful completion "
                    f"of in-progress {', '.join(in_progress_choices)}; those courses "
                    "remain in progress for degree reporting."
                )
    if proposal.deferred:
        text += " Deferred by the cap, but still eligible: " + ", ".join(
            entry.course.course_code for entry in proposal.deferred
        ) + "."
    text += (
        " These are evidence-based candidates from the supplied snapshot, not an "
        "official study plan or a guarantee of seats or timetable compatibility."
    )
    return AgentResponse(
        status="ok",
        intent="planner",
        text=text,
        planning=_payload(proposal),
    )
