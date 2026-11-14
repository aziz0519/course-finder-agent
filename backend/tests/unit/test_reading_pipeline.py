"""Synthetic PDFs keep safety/QA/storage tests runnable without the private corpus."""

from __future__ import annotations

import sqlite3

import pymupdf
import pytest

from app.domain.models import ReadingDocument
from app.ingestion.pdf_pipeline import NativePdfParser, sha256
from app.ingestion.quality_checks import check_reading
from app.ingestion.reading_models import ParsedReading
from app.ingestion.readings import ingest_reading
from app.ingestion.safety import classify_page
from app.retrieval.readings import LocalRetriever, ReadingScope


def authorized(document: ReadingDocument) -> ReadingScope:
    return ReadingScope(
        principal_id="verified-test-principal",
        course_ids=frozenset({document.course_id}),
        document_ids=frozenset({document.document_id}),
    )


def test_native_extraction_deduplicates_payload_not_placements(synthetic) -> None:
    root, document, review, repository = synthetic
    report = ingest_reading(document, root, repository, review)
    assert not report.errors and report.text_activatable and report.visual_qa_complete
    reading, directory = repository.active_candidates(
        document.course_id, frozenset({document.document_id})
    )[0]
    assert len(reading.assets) == 2
    assert len({a.asset_id for a in reading.assets}) == 2
    assert len({a.sha256 for a in reading.assets}) == 1
    assert len(list((directory / "assets").glob("*.png"))) == 1
    assert reading.pages[0].status == "native_text"


def test_unreviewed_text_cannot_activate(synthetic) -> None:
    root, document, _, repository = synthetic
    report = ingest_reading(document, root, repository)
    assert not report.text_activatable
    assert not repository.active_candidates(document.course_id, frozenset({document.document_id}))
    assert repository.inventory() and not repository.inventory()[0]["active"]


def test_new_unreviewed_version_does_not_replace_active(synthetic) -> None:
    root, document, review, repository = synthetic
    first = ingest_reading(document, root, repository, review)
    second = ingest_reading(document, root, repository)
    assert first.ingestion_version != second.ingestion_version
    active, _ = repository.active_candidates(document.course_id, frozenset({document.document_id}))[
        0
    ]
    assert active.ingestion_version == first.ingestion_version


def test_new_review_replaces_version_and_invalidates_old_citations(synthetic) -> None:
    root, document, review, repository = synthetic
    ingest_reading(document, root, repository, review)
    retriever = LocalRetriever(repository)
    old = retriever.search(authorized(document), document.course_id, "hydrogen").evidence[0]
    ingest_reading(document, root, repository, review.model_copy(update={"notes": "new review"}))
    with pytest.raises(PermissionError):
        retriever.resolve_citation(authorized(document), document.course_id, old.chunk_id)
    assert len(repository.inventory()) == 2
    assert sum(item["active"] for item in repository.inventory()) == 1


@pytest.mark.parametrize("fail_query", [False, True])
def test_search_closes_connection_after_commit_or_rollback(
    synthetic,
    monkeypatch: pytest.MonkeyPatch,
    fail_query: bool,
) -> None:
    root, document, review, repository = synthetic
    ingest_reading(document, root, repository, review)
    connect = sqlite3.connect
    events = []
    connections = []

    class TrackedConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            if fail_query and sql.startswith("SELECT rowid FROM scoped_fts"):
                assert self.in_transaction
                raise RuntimeError("simulated search failure")
            return super().execute(sql, parameters)

        def __exit__(self, exc_type, exc_value, traceback):
            events.append(("transaction_exit", exc_type))
            result = super().__exit__(exc_type, exc_value, traceback)
            assert not self.in_transaction
            return result

        def close(self):
            assert not self.in_transaction
            rows = self.execute("SELECT COUNT(*) FROM scoped_fts").fetchone()[0]
            assert rows == 0 if fail_query else rows > 0
            events.append(("close", None))
            super().close()

    def tracked_connect(database, *args, **kwargs):
        if database == ":memory:":
            connection = connect(database, *args, factory=TrackedConnection, **kwargs)
            connections.append(connection)
            return connection
        return connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", tracked_connect)
    retriever = LocalRetriever(repository)
    if fail_query:
        with pytest.raises(RuntimeError, match="simulated search failure"):
            retriever.search(authorized(document), document.course_id, "hydrogen")
    else:
        assert retriever.search(authorized(document), document.course_id, "hydrogen").evidence
    assert events == [
        ("transaction_exit", RuntimeError if fail_query else None),
        ("close", None),
    ]
    assert len(connections) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connections[0].execute("SELECT 1")


def test_extraction_method_survives_all_evidence_conversions(synthetic) -> None:
    root, document, review, repository = synthetic
    ingest_reading(document, root, repository, review)
    reading, _ = repository.active_candidates(
        document.course_id, frozenset({document.document_id})
    )[0]
    methods = {c.chunk_id: c.extraction_method for c in reading.chunks}
    retriever = LocalRetriever(repository)
    scope = authorized(document)
    result = retriever.search(scope, document.course_id, "hydrogen")
    assert result.evidence
    for evidence in result.evidence:
        assert evidence.extraction_method == methods[evidence.chunk_id]
        citation = retriever.resolve_citation(scope, document.course_id, evidence.chunk_id)
        assert citation.model_dump()["extraction_method"] == methods[evidence.chunk_id]
    visual = retriever.resolve_visual(
        scope,
        document.course_id,
        document.document_id,
        asset_id=reading.assets[0].asset_id,
    )
    assert visual.evidence and visual.evidence.adjacent_evidence
    assert all(
        e.extraction_method == methods[e.chunk_id] for e in visual.evidence.adjacent_evidence
    )


def test_checksum_and_stale_review_fail_closed(synthetic) -> None:
    root, document, review, repository = synthetic
    with pytest.raises(ValueError, match="stale review"):
        ingest_reading(
            document, root, repository, review.model_copy(update={"source_checksum": "0" * 64})
        )
    with pytest.raises(ValueError, match="checksum"):
        ingest_reading(document.model_copy(update={"file_checksum": "0" * 64}), root, repository)
    assert not repository.inventory()


@pytest.mark.parametrize("filename", ["../other.pdf", "/outside.pdf", "synthetic.txt"])
def test_path_and_file_type_validation(synthetic, filename: str) -> None:
    root, document, _, repository = synthetic
    with pytest.raises(ValueError):
        ingest_reading(document.model_copy(update={"source_filename": filename}), root, repository)


def test_page_count_mismatch_keeps_failed_job_inactive(synthetic) -> None:
    root, document, review, repository = synthetic
    with pytest.raises(ValueError, match="page count"):
        ingest_reading(document.model_copy(update={"page_count": 2}), root, repository, review)
    assert not repository.inventory()
    assert list(repository.root.glob("*/.staging-*/failure.json"))


def test_image_only_page_is_not_silently_ocrd_or_published(synthetic) -> None:
    root, document, _, repository = synthetic
    source = root / "scan.pdf"
    pdf = pymupdf.open()
    page = pdf.new_page()
    image = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 60), False)
    image.clear_with(255)
    page.insert_image(pymupdf.Rect(60, 60, 200, 200), stream=image.tobytes("png"))
    pdf.save(source)
    pdf.close()
    doc = document.model_copy(
        update={"source_filename": "scan.pdf", "file_checksum": sha256(source.read_bytes())}
    )
    report = ingest_reading(doc, root, repository)
    assert not report.text_activatable
    assert any("ocr_required" in warning for warning in report.warnings)


def test_quality_gate_detects_missing_page_artifact(synthetic) -> None:
    root, document, review, repository = synthetic
    ingest_reading(document, root, repository, review)
    reading, directory = repository.active_candidates(
        document.course_id, frozenset({document.document_id})
    )[0]
    (directory / reading.pages[0].page_image_uri).unlink()
    report = check_reading(reading, directory)
    assert not report.text_activatable and report.errors


def test_quality_gate_detects_broken_provenance(synthetic) -> None:
    root, document, review, repository = synthetic
    ingest_reading(document, root, repository, review)
    reading, directory = repository.active_candidates(
        document.course_id, frozenset({document.document_id})
    )[0]
    corrupt = reading.model_copy(
        update={"chunks": (reading.chunks[0].model_copy(update={"source_checksum": "bad"}),)}
    )
    assert "record_provenance_mismatch" in check_reading(corrupt, directory).errors


def test_failed_quality_gate_keeps_previous_version(synthetic) -> None:
    root, document, review, repository = synthetic
    first = ingest_reading(document, root, repository, review)

    class BrokenParser(NativePdfParser):
        @property
        def parser_id(self) -> str:
            return "test-broken-parser"

        def parse(self, *args, **kwargs) -> ParsedReading:
            reading = super().parse(*args, **kwargs)
            return reading.model_copy(update={"pages": ()})

    report = ingest_reading(document, root, repository, review, BrokenParser())
    assert not report.text_activatable and report.errors
    active, _ = repository.active_candidates(document.course_id, frozenset({document.document_id}))[
        0
    ]
    assert active.ingestion_version == first.ingestion_version


def test_interrupted_registry_publish_recovers_complete_artifacts(synthetic, monkeypatch) -> None:
    root, document, review, repository = synthetic
    publish = repository.publish

    def interrupted(*args, **kwargs):
        raise RuntimeError("simulated interruption before registry commit")

    monkeypatch.setattr(repository, "publish", interrupted)
    with pytest.raises(RuntimeError, match="interruption"):
        ingest_reading(document, root, repository, review)
    assert not repository.inventory()
    artifacts = list(repository.root.glob("*/*/parsed.json"))
    assert len(artifacts) == 1
    original = artifacts[0].read_bytes()
    monkeypatch.setattr(repository, "publish", publish)
    report = ingest_reading(document, root, repository, review)
    assert report.text_activatable and not report.errors
    assert len(repository.inventory()) == 1 and repository.inventory()[0]["active"]
    assert artifacts[0].read_bytes() == original


def test_changed_manifest_metadata_is_not_skipped_as_idempotent(synthetic) -> None:
    root, document, review, repository = synthetic
    ingest_reading(document, root, repository, review)
    with pytest.raises(ValueError, match="page count"):
        ingest_reading(document.model_copy(update={"page_count": 2}), root, repository, review)
    assert len(repository.inventory()) == 1 and repository.inventory()[0]["active"]


@pytest.mark.parametrize(
    ("course", "text", "label"),
    [
        ("PHYS 230", "safe sounding introduction", "restricted"),
        ("HIST 250", "historical introduction", "restricted"),
        ("HIST 210", "A discussion of uranium and nuclear weapons", "restricted"),
        ("PHYS 350", "Nuclear charge and electron levels", "safe"),
        ("ENGL 120", "The raven says nevermore", "safe"),
    ],
)
def test_safety_policy(course: str, text: str, label: str) -> None:
    assert classify_page(course, text) == label
