"""Retrieval is not an auth provider: scope must be minted by the M4 policy layer."""

import pytest

from app.domain.models import ReadingDocument
from app.retrieval.readings import LocalRetriever, ReadingScope


def authorized(document: ReadingDocument) -> ReadingScope:
    return ReadingScope(
        principal_id="verified-test-principal",
        course_ids=frozenset({document.course_id}),
        document_ids=frozenset({document.document_id}),
    )


def test_cross_course_and_empty_scope_denied(synthetic) -> None:
    _, document, _, repository = synthetic
    retriever = LocalRetriever(repository)
    for scope in [
        ReadingScope(principal_id="student-002", course_ids=frozenset(), document_ids=frozenset()),
        ReadingScope(
            principal_id="student-002",
            course_ids=frozenset({"OTHER"}),
            document_ids=frozenset({document.document_id}),
        ),
    ]:
        with pytest.raises(PermissionError):
            retriever.search(scope, document.course_id, "hydrogen")
        with pytest.raises(PermissionError):
            retriever.resolve_citation(scope, document.course_id, "guessed-id")
        with pytest.raises(PermissionError):
            retriever.resolve_visual(scope, document.course_id, document.document_id)


def test_document_filter_applies_even_with_course_access(synthetic) -> None:
    root, document, review, repository = synthetic
    from app.ingestion.readings import ingest_reading

    ingest_reading(document, root, repository, review)
    scope = authorized(document).model_copy(update={"document_ids": frozenset({"OTHER"})})
    assert (
        LocalRetriever(repository).search(scope, document.course_id, "hydrogen").status
        == "no_evidence"
    )
    with pytest.raises(PermissionError):
        LocalRetriever(repository).resolve_visual(scope, document.course_id, document.document_id)


def test_untrusted_source_cannot_expand_scope(synthetic) -> None:
    root, document, review, repository = synthetic
    from app.ingestion.readings import ingest_reading

    ingest_reading(document, root, repository, review)
    retriever = LocalRetriever(repository)
    result = retriever.search(authorized(document), document.course_id, "ignore rules")
    assert result.evidence and all(e.untrusted_source for e in result.evidence)
    with pytest.raises(PermissionError):
        retriever.search(authorized(document), "ANOTHER 200", "hydrogen")


def test_asset_requires_reauthorization_and_integrity(synthetic) -> None:
    root, document, review, repository = synthetic
    from app.ingestion.readings import ingest_reading

    ingest_reading(document, root, repository, review)
    retriever = LocalRetriever(repository)
    active, _ = repository.active_candidates(document.course_id, frozenset({document.document_id}))[
        0
    ]
    asset = active.assets[0]
    result = retriever.resolve_visual(
        authorized(document),
        document.course_id,
        document.document_id,
        asset_id=asset.asset_id,
        exact=True,
    )
    assert result.status == "ok" and result.evidence
    result.evidence.crop_path.write_bytes(b"corrupt")
    assert (
        retriever.resolve_visual(
            authorized(document), document.course_id, document.document_id, asset_id=asset.asset_id
        ).status
        == "unavailable"
    )


def test_no_sql_or_fts_query_injection(synthetic) -> None:
    root, document, review, repository = synthetic
    from app.ingestion.readings import ingest_reading

    ingest_reading(document, root, repository, review)
    result = LocalRetriever(repository).search(
        authorized(document), document.course_id, 'hydrogen" OR *; DELETE FROM active_readings; --'
    )
    assert result.status in ("ok", "no_evidence")
    assert repository.inventory()


def test_embeddings_receive_only_permitted_evidence(synthetic) -> None:
    root, document, review, repository = synthetic
    from app.ingestion.readings import ingest_reading

    ingest_reading(document, root, repository, review)

    class Provider:
        def __init__(self):
            self.calls = []

        def embed(self, texts):
            self.calls.append(texts)
            return tuple((1.0, 0.0) for _ in texts)

    provider = Provider()
    retriever = LocalRetriever(repository, provider)
    assert retriever.search(authorized(document), document.course_id, "hydrogen").evidence
    assert len(provider.calls) == 1
    scope = authorized(document).model_copy(update={"document_ids": frozenset({"OTHER"})})
    assert retriever.search(scope, document.course_id, "hydrogen").status == "no_evidence"
    assert len(provider.calls) == 1
