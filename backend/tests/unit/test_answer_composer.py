from app.agents.answer_composer import OfflineAnswerComposer
from app.retrieval.readings import Evidence


def evidence(text: str, chunk_id: str) -> Evidence:
    return Evidence(
        document_title="Bohr model",
        course_code="PHYS 350",
        document_id="phys350-bohr-model",
        source_checksum="a" * 64,
        ingestion_version="version",
        page_number=1,
        section=("Hydrogen spectrum",),
        excerpt=text,
        chunk_id=chunk_id,
        extraction_method="native_text",
        bbox=(0, 0, 10, 10),
    )


def test_offline_composer_selects_only_source_sentences() -> None:
    sources = (
        evidence(
            "Hydrogen has quantized energy levels. "
            "Transitions between levels emit light at particular frequencies.",
            "chunk-1",
        ),
        evidence("This unrelated sentence discusses historical context.", "chunk-2"),
    )
    result = OfflineAnswerComposer().compose(
        "How do energy-level transitions explain emitted light?", sources
    )
    assert 1 <= len(result.claims) <= 3
    assert result.claims[0].evidence_index == 0
    for claim in result.claims:
        assert claim.text in sources[claim.evidence_index].excerpt


def test_offline_composer_is_bounded() -> None:
    source = evidence("One. Two. Three. Four. Five.", "chunk")
    result = OfflineAnswerComposer().compose("Explain this", (source,))
    assert len(result.claims) == 3
