from __future__ import annotations

from pathlib import Path

import pytest

from app.ingestion.dataset import AcademicDataset
from app.ingestion.readings import ingest_reading, load_reviews
from app.repositories.conversations import ConversationRepository
from app.repositories.readings import ReadingRepository
from app.retrieval.readings import LocalRetriever, ReadingScope
from app.services.conversations import ConversationService


def _scope(dataset: AcademicDataset) -> ReadingScope:
    student = dataset.student("student-001")
    documents = {
        document.document_id
        for document in dataset.catalog.reading_documents
        if document.course_id in student.current_course_ids
    }
    return ReadingScope(
        principal_id="user-001",
        course_ids=frozenset(student.current_course_ids),
        document_ids=frozenset(documents),
    )


def _service(
    dataset: AcademicDataset,
    tmp_path: Path,
    reading_repository: ReadingRepository | None = None,
) -> ConversationService:
    return ConversationService(
        ConversationRepository(tmp_path / "conversations.sqlite3"),
        lambda: dataset,
        LocalRetriever(reading_repository or ReadingRepository(tmp_path / "empty-readings")),
    )


def test_planner_cap_is_recomputed_and_persisted(dataset: AcademicDataset, tmp_path: Path) -> None:
    service = _service(dataset, tmp_path)
    thread = service.create("user-001", "student-001")
    scope = _scope(dataset)

    first = service.handle_message(
        thread.thread_id,
        "user-001",
        scope,
        "What should I take in Spring 2027 to progress my degree? Keep it to 12 units.",
    )
    assert first.planning
    assert tuple(course.course_id for course in first.planning.recommended) == (
        "MATH 150",
        "PHYS 110",
        "PHYS 340",
    )
    assert first.planning.total_units == 12
    assert first.planning.catalogue_max_units == 16
    assert {item.source_type for item in first.planning.evidence} == {
        "catalogue",
        "student_record",
    }
    assert all(item.source_version for item in first.planning.evidence)
    assert len(first.trace_ids) == 2
    assert {
        run.trace.agent_name for run in service.repository.agent_runs(thread.thread_id, "user-001")
    } == {"supervisor", "planner"}

    second = service.handle_message(
        thread.thread_id,
        "user-001",
        scope,
        "I have accepted a part-time internship, so cap me at 8 units.",
    )
    assert second.planning
    assert tuple(course.course_id for course in second.planning.recommended) == (
        "MATH 150",
        "PHYS 110",
    )
    assert tuple(course.course_id for course in second.planning.deferred) == ("PHYS 340",)
    assert second.planning.total_units == 8
    assert dataset.catalog.policy.max_units_per_term == 16

    third = service.handle_message(
        thread.thread_id,
        "user-001",
        scope,
        "Which courses should I take?",
    )
    assert third.planning and third.planning.effective_unit_cap == 8


def test_service_denies_scope_from_another_principal(
    dataset: AcademicDataset, tmp_path: Path
) -> None:
    service = _service(dataset, tmp_path)
    thread = service.create("user-001", "student-001")
    bad_scope = _scope(dataset).model_copy(update={"principal_id": "user-002"})
    try:
        service.handle_message(thread.thread_id, "user-001", bad_scope, "Explain the Bohr model")
    except PermissionError:
        pass
    else:
        raise AssertionError("cross-principal scope was accepted")


def test_bohr_tutor_follow_up_uses_reviewed_visual(
    dataset: AcademicDataset, data_root: Path, tmp_path: Path
) -> None:
    document = dataset.catalog.document("phys350-bohr-model")
    assert document is not None
    source = data_root / "samples" / "course-materials" / document.source_filename
    if not source.is_file():
        pytest.skip("Optional Bohr model source PDF is unavailable")
    readings = ReadingRepository(tmp_path / "readings")
    reviews = load_reviews(data_root / "manifests" / "reading_qa.json")
    ingest_reading(
        document,
        data_root / "samples" / "course-materials",
        readings,
        reviews.documents[document.document_id],
    )
    service = _service(dataset, tmp_path, readings)
    thread = service.create("user-001", "student-001")
    scope = _scope(dataset)

    first = service.handle_message(
        thread.thread_id,
        "user-001",
        scope,
        "How does the Bohr model explain the lines in the hydrogen spectrum?",
    )
    assert first.status == "ok"
    assert first.citations
    assert all(citation.document_title == "Bohr model" for citation in first.citations)

    ambiguous = service.handle_message(
        thread.thread_id,
        "user-001",
        scope,
        "According to the diagram in that reading, how many electrons can "
        "the second energy level hold?",
    )
    assert ambiguous.status == "clarification_required"
    assert "Which figure/page" in ambiguous.text

    exact = service.handle_message(
        thread.thread_id,
        "user-001",
        scope,
        "I mean Figure 2. How many electrons can the second "
        "energy level hold according to its label?",
    )
    assert exact.status == "ok"
    assert "up to 8 electrons" in exact.text
    assert exact.citations[0].pdf_page_number == 4
    assert exact.citations[0].label == "Figure 2"


@pytest.mark.parametrize("cap", [0, -8])
def test_invalid_cap_clarifies_without_losing_preference(dataset, tmp_path, cap) -> None:
    service = _service(dataset, tmp_path)
    thread = service.create("user-001", "student-001")
    scope = _scope(dataset)
    service.handle_message(thread.thread_id, "user-001", scope, "Cap me at 12 units")
    response = service.handle_message(thread.thread_id, "user-001", scope, f"Cap me at {cap} units")
    assert response.status == "clarification_required"
    assert service.repository.get(thread.thread_id, "user-001").state.planning_unit_cap == 12
