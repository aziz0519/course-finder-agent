"""The conversation regression suite is a fixture, and it must match the engine.

The suite is reconstructed from AGENTS.md section 14. These tests prove it is
schema-valid and that its deterministic planner expectations are not stale.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

from app.domain.planning import propose_schedule
from app.ingestion.dataset import AcademicDataset


def _load_suite(data_root: Path) -> dict[str, Any]:
    path = data_root / "samples" / "test-conversations.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _load_schema(data_root: Path) -> dict[str, Any]:
    path = data_root / "schemas" / "test_conversations.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _conversation(suite: dict[str, Any], kind: str) -> dict[str, Any]:
    return next(item for item in suite["conversations"] if item["kind"] == kind)


def test_conversation_suite_matches_its_schema(data_root: Path) -> None:
    jsonschema.validate(_load_suite(data_root), _load_schema(data_root))


def test_planner_turns_match_the_deterministic_engine(
    dataset: AcademicDataset, data_root: Path
) -> None:
    suite = _load_suite(data_root)
    student = dataset.student(suite["student_id"])

    for turn in _conversation(suite, "planner")["turns"]:
        proposal = propose_schedule(
            student,
            dataset.catalog,
            requested_unit_cap=turn["request_unit_cap"],
        )

        assert set(proposal.recommended_course_ids) == set(turn["expected_recommended_courses"])
        assert proposal.total_units == turn["expected_total_units"]
        assert set(proposal.deferred_course_ids) == set(turn["expected_deferred_courses"])
        assert set(proposal.alternative_course_ids) == set(turn["expected_alternative_courses"])
        assert proposal.catalogue_max_units == turn["expected_catalogue_max_units"]
        assert proposal.unit_cap == min(
            turn["request_unit_cap"], dataset.catalog.policy.max_units_per_term
        )


def test_tutor_turns_resolve_to_the_supplied_reading(
    dataset: AcademicDataset, data_root: Path
) -> None:
    suite = _load_suite(data_root)

    for turn in _conversation(suite, "tutor")["turns"]:
        course = dataset.catalog.course(turn["expected_course_code"])
        documents = [
            dataset.catalog.document(document_id) for document_id in course.reading_document_ids
        ]
        document = next(
            (
                candidate
                for candidate in documents
                if candidate is not None
                and candidate.title == turn["expected_document_title"]
            ),
            None,
        )

        assert document is not None
        assert document.source_filename == Path(turn["expected_source_filename"]).name

        if turn["value_verification_status"] == "pending_diagram_inspection":
            assert turn.get("expected_answer_value") is None
