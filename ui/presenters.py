"""Pure formatting helpers. No Gradio or network imports, so they are unit-testable."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from ui.api_client import ApiError

STATUS_NOTES = {
    "ok": "",
    "clarification_required": (
        "Clarification needed — say which figure, page, or reading you mean."
    ),
    "insufficient_evidence": (
        "The supplied reading does not contain enough evidence for that answer."
    ),
    "unsupported": "The supplied course data does not contain this information.",
}

REQUIREMENT_STATES = {
    "satisfied": "Satisfied",
    "in_progress": "In progress",
    "remaining": "Remaining",
    "unable_to_determine": "Unable to determine",
}


def escape(text: object) -> str:
    """Treat model and source text as data, never as markup or instructions."""

    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _quote(text: str) -> str:
    lines = escape(text).splitlines() or [""]
    return "\n".join(f"> {line}" if line else ">" for line in lines)


def status_note(status: str) -> str:
    return STATUS_NOTES.get(status, "")


def assistant_content(text: str, status: str) -> str:
    body = escape(text)
    note = status_note(status)
    if not note:
        return body
    return f"{body}\n\n---\n*{note}*"


def profile_markdown(profile: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            f"### {escape(profile.get('student_id', 'Student'))}",
            f"**Level:** {escape(profile.get('academic_level', 'unknown'))}  ",
            f"**Programme:** {escape(profile.get('program_id', 'unknown'))}  ",
            f"**Adviser:** {escape(profile.get('adviser_id', 'unassigned'))}",
        ]
    )


def course_rows(profile: Mapping[str, Any]) -> list[list[str]]:
    return [
        [
            escape(item.get("course_code", "")),
            escape(item.get("term", "")),
            escape(item.get("status", "")),
        ]
        for item in profile.get("current_courses", ())
    ]


def materials_rows(materials: Mapping[str, Any]) -> list[list[str]]:
    rows: list[list[str]] = []
    for course in materials.get("courses", ()):
        readings = course.get("readings") or ()
        if not readings:
            rows.append(
                [
                    escape(course.get("course_code", "")),
                    "No reading mapped",
                    "—",
                    "—",
                    "—",
                ]
            )
            continue
        for reading in readings:
            if reading.get("ingested"):
                review = (
                    f"{reading.get('approved_assets', 0)} of "
                    f"{reading.get('total_assets', 0)} visuals approved"
                )
                state = "Reading available"
            else:
                review = "Not ingested"
                state = "Unavailable"
            rows.append(
                [
                    escape(course.get("course_code", "")),
                    escape(reading.get("title", "")),
                    str(reading.get("page_count") or "—"),
                    review,
                    state,
                ]
            )
    return rows


def progress_rows(progress: Mapping[str, Any]) -> list[list[str]]:
    rows = []
    for group in progress.get("requirement_groups", ()):
        rows.append(
            [
                escape(group.get("label", group.get("group_id", ""))),
                REQUIREMENT_STATES.get(group.get("state", ""), escape(group.get("state", ""))),
                str(group.get("required_count", "")),
                ", ".join(escape(item) for item in group.get("completed_members", ())) or "—",
                ", ".join(escape(item) for item in group.get("in_progress_members", ())) or "—",
                str(group.get("courses_short", "")),
            ]
        )
    return rows


def plan_overview(response: Mapping[str, Any]) -> str:
    plan = response.get("plan", {})
    requested = plan.get("requested_unit_cap")
    cap_line = (
        f"Requested cap **{requested} units** · catalogue maximum "
        f"**{plan.get('catalogue_max_units', '?')} units**"
        if requested is not None
        else f"Catalogue maximum **{plan.get('catalogue_max_units', '?')} units**"
    )
    lines = [
        f"### {escape(plan.get('target_term', 'Next term'))} — "
        f"{plan.get('total_units', 0)} units proposed",
        cap_line,
        "",
        f"**Effective cap:** {plan.get('effective_unit_cap', '?')} units",
        "",
        escape(response.get("disclaimer", "")),
    ]
    evidence = plan.get("evidence") or ()
    if evidence:
        lines.append("")
        lines.append("**Sources:**")
        lines.extend(
            f"- {escape(item.get('description', ''))} "
            f"({escape(item.get('source_type', ''))} v{escape(item.get('source_version', ''))})"
            for item in evidence
        )
    return "\n".join(lines)


def plan_rows(courses: Iterable[Mapping[str, Any]]) -> list[list[str]]:
    return [
        [
            escape(course.get("course_id", "")),
            escape(course.get("title", "")),
            str(course.get("units", "")),
            "; ".join(escape(item) for item in course.get("explanations", ())),
        ]
        for course in courses
    ]


def deferred_markdown(response: Mapping[str, Any]) -> str:
    plan = response.get("plan", {})
    deferred = plan.get("deferred") or ()
    alternatives = plan.get("alternatives") or ()
    lines: list[str] = []
    if deferred:
        lines.append("**Deferred, not ineligible:**")
        lines.extend(
            f"- {escape(item.get('course_id', ''))} — {escape(item.get('title', ''))}"
            for item in deferred
        )
    if alternatives:
        if lines:
            lines.append("")
        lines.append("**Other eligible alternatives:**")
        lines.extend(
            f"- {escape(item.get('course_id', ''))} — {escape(item.get('title', ''))}"
            for item in alternatives
        )
    return "\n".join(lines)


def citation_label(citation: Mapping[str, Any]) -> str:
    label = (
        f"{citation.get('course_code', '')} · {citation.get('document_title', '')} · "
        f"p. {citation.get('pdf_page_number', '?')}"
    )
    if citation.get("label"):
        label += f" · {citation['label']}"
    return label


def citation_choices(citations: Iterable[Mapping[str, Any]]) -> list[tuple[str, int]]:
    return [(citation_label(item), index) for index, item in enumerate(citations)]


def citation_detail(evidence: Mapping[str, Any], citation: Mapping[str, Any]) -> str:
    section = " → ".join(evidence.get("section") or ())
    lines = [
        f"**{escape(evidence.get('course_code', ''))} — "
        f"{escape(evidence.get('document_title', ''))}, "
        f"PDF p. {evidence.get('page_number', '?')}**"
        + (f" · {escape(citation.get('label'))}" if citation.get("label") else ""),
        "",
        _quote(evidence.get("excerpt", "")),
        "",
        f"<small>Chunk {escape(evidence.get('chunk_id', ''))} · "
        f"{escape(evidence.get('extraction_method', ''))} extraction"
        + (f" · {escape(section)}" if section else "")
        + f" · version {escape(evidence.get('ingestion_version', ''))}</small>",
    ]
    return "\n".join(lines)


def error_text(exc: ApiError) -> str:
    if exc.status_code == 401:
        return "Your session has expired or is not valid. Sign in again."
    if exc.status_code == 403:
        return "This action is not permitted for your role."
    if exc.status_code == 404:
        return "That record is unavailable in your authorized scope."
    if exc.status_code == 429:
        return "Too many attempts. Wait a moment and try again."
    if exc.status_code in (409, 422, 503):
        return escape(exc.detail)
    return f"Request failed ({exc.status_code}): {escape(exc.detail)}"


def job_markdown(job: Mapping[str, Any]) -> str:
    report = job.get("report")
    lines = [
        f"**Job:** {escape(job.get('job_id', ''))}",
        f"**Status:** {escape(job.get('status', ''))}",
        f"**Dataset version:** {escape(job.get('dataset_version', ''))}",
    ]
    if report:
        lines.append("")
        lines.append("```json")
        import json

        lines.append(escape(json.dumps(report, indent=2, sort_keys=True)))
        lines.append("```")
    return "\n".join(lines)
