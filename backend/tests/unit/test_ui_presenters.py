from __future__ import annotations

from typing import Any

from ui import presenters
from ui.api_client import ApiError

PLAN_RESPONSE: dict[str, Any] = {
    "student_id": "student-001",
    "plan": {
        "target_term": "Spring 2027",
        "catalogue_max_units": 16,
        "effective_unit_cap": 12,
        "requested_unit_cap": 12,
        "total_units": 12,
        "recommended": [
            {
                "course_id": "PHYS 110",
                "title": "Physics I",
                "units": 4,
                "explanations": ["Core requirement", "<script>alert(1)</script>"],
            }
        ],
        "deferred": [{"course_id": "PHYS 340", "title": "Elective", "units": 4}],
        "alternatives": [{"course_id": "ENGL 130", "title": "Literature", "units": 4}],
        "evidence": [
            {
                "source_type": "catalogue",
                "source_version": "v1",
                "description": "Catalogue Spring 2027 offerings",
            }
        ],
    },
    "disclaimer": "Suggestions only.",
}


def test_assistant_content_escapes_source_and_adds_status_note() -> None:
    rendered = presenters.assistant_content("<b>claim</b>", "clarification_required")
    assert "&lt;b&gt;" in rendered
    assert "<b>" not in rendered
    assert "Clarification needed" in rendered

    assert presenters.status_note("ok") == ""
    assert "does not contain" in presenters.status_note("insufficient_evidence")
    assert "does not contain this information" in presenters.status_note("unsupported")


def test_materials_rows_mark_unavailable_and_review_state() -> None:
    rows = presenters.materials_rows(
        {
            "courses": [
                {
                    "course_code": "PHYS 350",
                    "readings": [
                        {
                            "title": "Bohr model",
                            "page_count": 12,
                            "ingested": True,
                            "approved_assets": 2,
                            "total_assets": 9,
                        }
                    ],
                },
                {"course_code": "HIST 210", "readings": []},
            ]
        }
    )
    assert rows[0] == [
        "PHYS 350",
        "Bohr model",
        "12",
        "2 of 9 visuals approved",
        "Reading available",
    ]
    assert rows[1][1] == "No reading mapped"


def test_progress_rows_map_states_and_members() -> None:
    rows = presenters.progress_rows(
        {
            "requirement_groups": [
                {
                    "group_id": "history",
                    "label": "History",
                    "state": "satisfied",
                    "required_count": 1,
                    "completed_members": ["HIST 250"],
                    "in_progress_members": [],
                    "remaining_options": [],
                    "courses_short": 0,
                }
            ]
        }
    )
    assert rows == [["History", "Satisfied", "1", "HIST 250", "—", "0"]]


def test_plan_view_reports_caps_sources_and_escapes_cells() -> None:
    overview = presenters.plan_overview(PLAN_RESPONSE)
    assert "Spring 2027" in overview
    assert "12 units proposed" in overview
    assert "Requested cap" in overview
    assert "catalogue maximum" in overview.lower()
    assert "Catalogue Spring 2027 offerings" in overview
    assert "Suggestions only." in overview

    rows = presenters.plan_rows(PLAN_RESPONSE["plan"]["recommended"])
    assert rows[0][0] == "PHYS 110"
    assert "&lt;script&gt;" in rows[0][3]
    assert "<script>" not in rows[0][3]

    notes = presenters.deferred_markdown(PLAN_RESPONSE)
    assert "Deferred, not ineligible" in notes
    assert "PHYS 340" in notes
    assert "ENGL 130" in notes


def test_plan_view_without_requested_cap() -> None:
    response = {
        "plan": {
            "target_term": "Spring 2027",
            "catalogue_max_units": 16,
            "effective_unit_cap": 16,
            "requested_unit_cap": None,
            "total_units": 4,
            "recommended": [],
        },
        "disclaimer": "Suggestions only.",
    }
    overview = presenters.plan_overview(response)
    assert "Requested cap" not in overview
    assert "Catalogue maximum" in overview


def test_citation_views_include_page_and_source_metadata() -> None:
    citation = {
        "course_code": "PHYS 350",
        "document_title": "Bohr model",
        "pdf_page_number": 4,
        "label": "Figure 2",
        "chunk_id": "chunk-1",
    }
    assert presenters.citation_label(citation) == (
        "PHYS 350 · Bohr model · p. 4 · Figure 2"
    )
    choices = presenters.citation_choices([citation])
    assert choices == [("PHYS 350 · Bohr model · p. 4 · Figure 2", 0)]

    detail = presenters.citation_detail(
        {
            "course_code": "PHYS 350",
            "document_title": "Bohr model",
            "page_number": 4,
            "section": ("The Bohr atom", "Energy levels"),
            "excerpt": "Line one\nLine two",
            "chunk_id": "chunk-1",
            "extraction_method": "native",
            "ingestion_version": "abc123",
        },
        citation,
    )
    assert "PDF p. 4" in detail
    assert "> Line one" in detail
    assert "> Line two" in detail
    assert "native extraction" in detail
    assert "The Bohr atom → Energy levels" in detail


def test_error_messages_are_actionable_and_redacted() -> None:
    assert "Sign in again" in presenters.error_text(ApiError(401, "Authentication required."))
    assert "not permitted" in presenters.error_text(ApiError(403, "Admin role required."))
    assert "authorized scope" in presenters.error_text(ApiError(404, "missing"))
    assert "Too many attempts" in presenters.error_text(ApiError(429, "slow down"))
    assert presenters.error_text(ApiError(422, "Only Spring 2027 is supported")) == (
        "Only Spring 2027 is supported"
    )
    assert presenters.error_text(ApiError(503, "unavailable")) == "unavailable"


def test_job_report_is_escaped_json() -> None:
    rendered = presenters.job_markdown(
        {
            "job_id": "job-1",
            "status": "completed",
            "dataset_version": "v1",
            "report": {"pages": 64, "note": "<script>"},
        }
    )
    assert "job-1" in rendered
    assert "completed" in rendered
    assert "&lt;script&gt;" in rendered
    assert "<script>" not in rendered
