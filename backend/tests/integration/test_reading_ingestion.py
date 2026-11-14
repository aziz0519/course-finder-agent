"""M2 corpus regressions: actual bytes, no external models or credentials."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.ingestion.dataset import AcademicDataset
from app.ingestion.quality_checks import check_reading
from app.ingestion.reading_models import ParsedReading, ReviewManifest
from app.ingestion.readings import ingest_reading, load_reviews
from app.repositories.readings import ReadingRepository
from app.retrieval.readings import LocalRetriever, ReadingScope


@pytest.fixture(scope="module")
def corpus(
    dataset: AcademicDataset,
    data_root: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> ReadingRepository:
    materials = data_root / "samples" / "course-materials"
    if not all(
        (materials / d.source_filename).is_file() for d in dataset.catalog.reading_documents
    ):
        pytest.skip("approved PDF fixtures are not installed; synthetic M2 tests still run")
    reviews = load_reviews(data_root / "manifests" / "reading_qa.json")
    repository = ReadingRepository(tmp_path_factory.mktemp("m2-corpus"))
    for document in dataset.catalog.reading_documents:
        report = ingest_reading(
            document, materials, repository, reviews.documents[document.document_id]
        )
        assert not report.errors
    return repository


def scope(course: str, document_id: str) -> ReadingScope:
    return ReadingScope(
        principal_id="server-authorized-test-user",
        course_ids=frozenset({course}),
        document_ids=frozenset({document_id}),
    )


@pytest.mark.parametrize(
    ("course", "document_id", "pages"),
    [
        ("PHYS 230", "phys230-critical-mass", 11),
        ("PHYS 350", "phys350-bohr-model", 12),
        ("ENGL 120", "engl120-the-raven", 15),
        ("HIST 210", "hist210-niels-bohr", 17),
        ("HIST 250", "hist250-demon-core", 9),
    ],
)
def test_corpus_page_coverage_and_provenance(
    corpus: ReadingRepository,
    course: str,
    document_id: str,
    pages: int,
) -> None:
    reading, directory = corpus.active_candidates(course, frozenset({document_id}))[0]
    assert len(reading.pages) == pages
    assert all(p.has_text_layer and p.text_reviewed for p in reading.pages)
    assert reading.ocr_model is None and reading.vlm_model is None
    assert not check_reading(reading, directory).errors
    assert (directory / "source.pdf").is_file()
    assert list(directory.glob("contact-sheet-*.png"))
    assert all(c.source_checksum == reading.source_checksum for c in reading.chunks)
    assert all(a.ingestion_version == reading.ingestion_version for a in reading.assets)
    assert reading.attribution.source_attribution
    assert reading.attribution.license_id == "CC-BY-SA"


def test_reference_inventory_and_no_guessed_formulas(corpus: ReadingRepository) -> None:
    reading, _ = corpus.active_candidates("PHYS 230", frozenset({"phys230-critical-mass"}))[0]
    for kind, expected in (
        ("figure", {1, 5, 10}),
        ("table", {6, 9, 11}),
        ("chart", {9}),
        ("equation", {7}),
    ):
        assert {a.pdf_page_number for a in reading.assets if a.visual_type == kind} == expected
    equation = next(a for a in reading.assets if a.visual_type == "equation")
    assert equation.latex is None and "equation_unparsed" in equation.warnings
    assert all(c.safety_label == "restricted" for c in reading.chunks)
    assert all(a.safety_label == "restricted" for a in reading.assets)


def test_bohr_caption_retrieval_and_citation_round_trip(corpus: ReadingRepository) -> None:
    retriever = LocalRetriever(corpus)
    authorized = scope("PHYS 350", "phys350-bohr-model")
    results = retriever.search(authorized, "PHYS 350", "hydrogen spectrum transitions Balmer")
    assert results.status == "ok"
    assert any(e.page_number == 1 and "Balmer" in e.excerpt for e in results.evidence)
    for evidence in results.evidence:
        assert evidence.document_title == "Bohr model"
        assert retriever.resolve_citation(authorized, "PHYS 350", evidence.chunk_id) == evidence
        assert evidence.untrusted_source


def test_bohr_verified_shell_diagram(corpus: ReadingRepository, data_root: Path) -> None:
    retriever = LocalRetriever(corpus)
    result = retriever.resolve_visual(
        scope("PHYS 350", "phys350-bohr-model"),
        "PHYS 350",
        "phys350-bohr-model",
        page_number=4,
        visual_type="figure",
        exact=True,
    )
    assert result.status == "ok" and result.evidence
    assert result.evidence.asset.label == "Figure 2"
    assert result.evidence.crop_path.is_file()
    assert result.evidence.asset.pdf_page_number == 4
    assert result.evidence.adjacent_evidence
    # Value verified by inspecting the supplied Figure 2, not general model knowledge.
    assert result.evidence.asset.source_transcription == (
        "The second and third energy levels can each contain up to 8 electrons."
    )
    suite = json.loads((data_root / "samples" / "test-conversations.json").read_text())
    tutor = next(c for c in suite["conversations"] if c["kind"] == "tutor")
    match = re.search(r"up to (\d+) electrons", result.evidence.asset.source_transcription)
    assert match and int(match[1]) == tutor["turns"][1]["expected_answer_value"]


def test_bohr_equation_abstention_and_ambiguous_diagram(corpus: ReadingRepository) -> None:
    retriever = LocalRetriever(corpus)
    authorized = scope("PHYS 350", "phys350-bohr-model")
    assert (
        retriever.search(authorized, "PHYS 350", "Explain that equation").status
        == "visual_required"
    )
    result = retriever.resolve_visual(
        authorized,
        "PHYS 350",
        "phys350-bohr-model",
        visual_type="figure",
    )
    assert result.status == "clarification_required" and len(result.candidate_asset_ids) == 2
    assert (
        retriever.resolve_visual(
            authorized,
            "PHYS 350",
            "phys350-bohr-model",
            page_number=7,
            visual_type="equation",
            exact=True,
        ).status
        == "unavailable"
    )


def test_reviewed_table_matches_render(corpus: ReadingRepository) -> None:
    result = LocalRetriever(corpus).resolve_visual(
        scope("ENGL 120", "engl120-the-raven"),
        "ENGL 120",
        "engl120-the-raven",
        page_number=1,
        visual_type="table",
        exact=True,
    )
    assert result.status == "ok" and result.evidence
    rows = result.evidence.asset.structured_rows
    assert rows[0] == ("Item", "Detail")
    assert len(rows) == 7 and all(len(row) == 2 for row in rows)
    assert rows[-1] == ("Lines", "108")


def test_unverified_table_abstains(corpus: ReadingRepository) -> None:
    assert (
        LocalRetriever(corpus)
        .resolve_visual(
            scope("ENGL 120", "engl120-the-raven"),
            "ENGL 120",
            "engl120-the-raven",
            page_number=9,
            visual_type="table",
            exact=True,
        )
        .status
        == "unavailable"
    )


@pytest.mark.parametrize(
    ("course", "document_id"),
    [("PHYS 230", "phys230-critical-mass"), ("HIST 250", "hist250-demon-core")],
)
def test_restricted_content_never_leaks(
    corpus: ReadingRepository,
    course: str,
    document_id: str,
) -> None:
    retriever = LocalRetriever(corpus)
    authorized = scope(course, document_id)
    assert retriever.search(authorized, course, "critical mass").status == "no_evidence"
    assert retriever.resolve_visual(authorized, course, document_id).status == "unavailable"
    reading, _ = corpus.active_candidates(course, frozenset({document_id}))[0]
    with pytest.raises(PermissionError):
        retriever.resolve_citation(authorized, course, reading.chunks[0].chunk_id)


def test_corpus_reingestion_is_idempotent(
    corpus: ReadingRepository,
    dataset: AcademicDataset,
    data_root: Path,
) -> None:
    reviews = load_reviews(data_root / "manifests" / "reading_qa.json")
    before = corpus.inventory()
    for doc in dataset.catalog.reading_documents:
        ingest_reading(
            doc,
            data_root / "samples" / "course-materials",
            corpus,
            reviews.documents[doc.document_id],
        )
    assert corpus.inventory() == before


def test_manifest_is_strict_and_checksum_bound(data_root: Path) -> None:
    manifest = ReviewManifest.model_validate_json(
        (data_root / "manifests" / "reading_qa.json").read_text()
    )
    assert len(manifest.documents) == 5
    raw = json.loads(manifest.model_dump_json())
    raw["documents"]["phys350-bohr-model"]["invented_field"] = True
    with pytest.raises(ValueError):
        ReviewManifest.model_validate(raw)


@pytest.mark.parametrize(
    ("course", "document_id", "query", "expected_page"),
    [
        ("ENGL 120", "engl120-the-raven", "Lenore nevermore raven", 1),
        ("HIST 210", "hist210-niels-bohr", "early life education Copenhagen 1885", 3),
    ],
)
def test_other_readings_have_grounded_prose(
    corpus: ReadingRepository,
    course: str,
    document_id: str,
    query: str,
    expected_page: int,
) -> None:
    result = LocalRetriever(corpus).search(scope(course, document_id), course, query, limit=10)
    assert result.status == "ok"
    assert any(e.page_number == expected_page for e in result.evidence)
    assert all(e.document_id == document_id for e in result.evidence)


def test_table_chunks_repeat_source_header(corpus: ReadingRepository) -> None:
    reading, _ = corpus.active_candidates("ENGL 120", frozenset({"engl120-the-raven"}))[0]
    table_chunks = [
        c for c in reading.chunks if c.content_type == "table" and c.pdf_page_number == 1
    ]
    assert len(table_chunks) == 2
    assert all(c.text.startswith("Item | Detail\n") and c.asset_refs for c in table_chunks)


def test_parsed_json_round_trip(corpus: ReadingRepository) -> None:
    reading, root = corpus.active_candidates("ENGL 120", frozenset({"engl120-the-raven"}))[0]
    assert ParsedReading.model_validate_json((root / "parsed.json").read_text()) == reading
