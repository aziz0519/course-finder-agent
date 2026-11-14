"""Course/document-scoped evidence retrieval. This module never generates an answer.

M4 must construct ReadingScope from its verified principal and policy result, never
from browser/LLM-supplied role or student IDs. Every entry point rechecks that scope.
FTS5 runs on an already-filtered candidate set, so neither keyword nor optional
vector ranking can see another course, inactive version, or quarantined passage.
"""

from __future__ import annotations

import math
import re
import sqlite3
from pathlib import Path
from typing import Literal, Protocol

from pydantic import Field

from app.domain.models import DomainModel
from app.ingestion.pdf_pipeline import sha256
from app.ingestion.reading_models import FigureAsset, ParsedReading, ReadingChunk, VisualType
from app.repositories.readings import ReadingRepository


class ReadingScope(DomainModel):
    principal_id: str = Field(min_length=1)
    course_ids: frozenset[str]
    document_ids: frozenset[str]


class Evidence(DomainModel):
    document_title: str
    course_code: str
    document_id: str
    source_checksum: str
    ingestion_version: str
    page_number: int = Field(ge=1)
    section: tuple[str, ...]
    excerpt: str
    chunk_id: str
    bbox: tuple[float, float, float, float]
    asset_refs: tuple[str, ...] = ()
    untrusted_source: Literal[True] = True


class SearchResult(DomainModel):
    evidence: tuple[Evidence, ...] = ()
    status: Literal["ok", "no_evidence", "visual_required"]
    note: str | None = None


class VisualEvidence(DomainModel):
    document_title: str
    asset: FigureAsset
    # Only a checked crop, not the original PDF or whole page.
    crop_path: Path
    adjacent_evidence: tuple[Evidence, ...]


class VisualResult(DomainModel):
    status: Literal["ok", "unavailable", "clarification_required"]
    evidence: VisualEvidence | None = None
    candidate_asset_ids: tuple[str, ...] = ()
    note: str | None = None


class Embeddings(Protocol):
    """Optional configured provider; only permitted candidates are embedded.

    Production adapters must enforce timeout/retry/token budgets and redacted logs.
    No external provider is enabled by default.
    """

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...


class Retriever(Protocol):
    def search(
        self,
        scope: ReadingScope,
        course_id: str,
        query: str,
        *,
        limit: int = 5,
    ) -> SearchResult: ...

    def resolve_citation(
        self,
        scope: ReadingScope,
        course_id: str,
        chunk_id: str,
    ) -> Evidence: ...


VISUAL_QUERY = re.compile(
    r"\b(diagram|figure|chart|table|equation|formula|graph|plot|image)\b", re.IGNORECASE
)
STOP_WORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "do",
        "does",
        "explain",
        "for",
        "from",
        "how",
        "i",
        "in",
        "is",
        "it",
        "me",
        "model",
        "my",
        "of",
        "on",
        "or",
        "please",
        "reading",
        "show",
        "that",
        "the",
        "this",
        "to",
        "up",
        "what",
        "when",
        "which",
        "with",
    ]
)


def _evidence(reading: ParsedReading, chunk: ReadingChunk) -> Evidence:
    return Evidence(
        document_title=reading.document.title,
        course_code=chunk.course_id,
        document_id=chunk.document_id,
        source_checksum=chunk.source_checksum,
        ingestion_version=chunk.ingestion_version,
        page_number=chunk.pdf_page_number,
        section=chunk.section_path,
        excerpt=chunk.text,
        chunk_id=chunk.chunk_id,
        bbox=chunk.bbox,
        asset_refs=chunk.asset_refs,
    )


class LocalRetriever:
    def __init__(self, repository: ReadingRepository, embeddings: Embeddings | None = None):
        self.repository = repository
        self.embeddings = embeddings

    def _readings(
        self,
        scope: ReadingScope,
        course_id: str,
    ) -> list[tuple[ParsedReading, Path]]:
        if course_id not in scope.course_ids or not scope.document_ids:
            raise PermissionError("reading access denied")
        return self.repository.active_candidates(course_id, scope.document_ids)

    @staticmethod
    def _allowed_chunk(chunk: ReadingChunk) -> bool:
        return (
            chunk.safety_label == "safe"
            and chunk.text_reviewed
            and chunk.extraction_confidence >= 0.8
            and chunk.content_type in ("text", "caption")
        )

    def search(
        self,
        scope: ReadingScope,
        course_id: str,
        query: str,
        *,
        limit: int = 5,
    ) -> SearchResult:
        if not query.strip() or len(query) > 4000 or not 1 <= limit <= 20:
            raise ValueError("query must have 1-4000 characters; limit must be 1-20")
        readings = self._readings(scope, course_id)
        if VISUAL_QUERY.search(query):
            return SearchResult(
                status="visual_required",
                note="Resolve a reviewed visual; prose alone is insufficient.",
            )
        candidates = [
            (reading, chunk)
            for reading, _ in readings
            for chunk in reading.chunks
            if self._allowed_chunk(chunk)
        ]
        if not candidates:
            return SearchResult(
                status="no_evidence", note="No approved source evidence is available in this scope."
            )
        tokens = list(
            dict.fromkeys(
                token
                for token in re.findall(r"\w+", query.lower(), re.UNICODE)
                if token not in STOP_WORDS
            )
        )[:40]
        if not tokens:
            return SearchResult(
                status="no_evidence", note="Please specify a topic from the reading."
            )
        # Populate a private, ephemeral FTS index *after* applying every filter.
        with sqlite3.connect(":memory:") as db:
            db.execute(
                "CREATE VIRTUAL TABLE scoped_fts USING fts5(text, tokenize='porter unicode61')"
            )
            db.executemany(
                "INSERT INTO scoped_fts(rowid,text) VALUES (?,?)",
                ((index + 1, chunk.text) for index, (_, chunk) in enumerate(candidates)),
            )
            rows = db.execute(
                "SELECT rowid FROM scoped_fts WHERE scoped_fts MATCH ? "
                "ORDER BY bm25(scoped_fts),rowid LIMIT 60",
                (" OR ".join(f'"{token}"' for token in tokens),),
            ).fetchall()
        lexical = [row[0] - 1 for row in rows]
        ranked = lexical
        if self.embeddings:
            # Bounded per-request work; a real embedding index may replace this seam.
            candidate_ids = lexical[:60]
            if candidate_ids:
                vectors = self.embeddings.embed(
                    (query, *(candidates[i][1].text for i in candidate_ids))
                )
                if len(vectors) != len(candidate_ids) + 1:
                    raise ValueError("embedding provider returned wrong vector count")
                scores = {}
                for position, index in enumerate(candidate_ids):
                    similarity = _cosine(vectors[0], vectors[position + 1])
                    scores[index] = 1 / (60 + position + 1) + max(0, similarity) / 60
                ranked = sorted(candidate_ids, key=lambda i: (-scores[i], i))
        evidence = tuple(_evidence(*candidates[index]) for index in ranked[:limit])
        return SearchResult(
            evidence=evidence,
            status="ok" if evidence else "no_evidence",
            note=None if evidence else "The approved reading evidence does not contain that topic.",
        )

    def resolve_citation(
        self,
        scope: ReadingScope,
        course_id: str,
        chunk_id: str,
    ) -> Evidence:
        for reading, _ in self._readings(scope, course_id):
            for chunk in reading.chunks:
                if chunk.chunk_id == chunk_id and self._allowed_chunk(chunk):
                    return _evidence(reading, chunk)
        raise PermissionError("citation unavailable in the active authorized evidence")

    def resolve_visual(
        self,
        scope: ReadingScope,
        course_id: str,
        document_id: str,
        *,
        asset_id: str | None = None,
        page_number: int | None = None,
        visual_type: VisualType | None = None,
        exact: bool = False,
    ) -> VisualResult:
        """Use a thread's explicit document/asset antecedent; never search other documents."""
        readings = self._readings(scope, course_id)
        if document_id not in scope.document_ids:
            raise PermissionError("reading access denied")
        matches = [
            (reading, root, asset)
            for reading, root in readings
            if reading.document.document_id == document_id
            for asset in reading.assets
            if asset.safety_label == "safe"
            and (asset_id is None or asset.asset_id == asset_id)
            and (page_number is None or asset.pdf_page_number == page_number)
            and (visual_type is None or asset.visual_type == visual_type)
        ]
        if len(matches) > 1:
            return VisualResult(
                status="clarification_required",
                candidate_asset_ids=tuple(a.asset_id for _, _, a in matches),
                note="Which figure/page do you mean?",
            )
        if not matches:
            return VisualResult(
                status="unavailable", note="No authorized visual matches that reference."
            )
        reading, root, asset = matches[0]
        if asset.review_status != "approved" or (exact and not asset.exact_values_verified):
            return VisualResult(
                status="unavailable",
                note="This visual is unverified for the claim; no exact answer is available.",
            )
        if asset.visual_type == "table" and exact and not asset.structured_rows:
            return VisualResult(status="unavailable", note="Table structure is unverified.")
        if asset.visual_type == "chart" and exact:
            return VisualResult(
                status="unavailable", note="Exact chart digitization is not implemented."
            )
        path = (root / asset.asset_uri).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            return VisualResult(status="unavailable", note="The source crop is unavailable.")
        if sha256(path.read_bytes()) != asset.sha256:
            return VisualResult(status="unavailable", note="Source crop integrity check failed.")
        adjacent = tuple(
            _evidence(reading, c)
            for c in reading.chunks
            if c.pdf_page_number == asset.pdf_page_number and self._allowed_chunk(c)
        )
        return VisualResult(
            status="ok",
            evidence=VisualEvidence(
                document_title=reading.document.title,
                asset=asset,
                crop_path=path,
                adjacent_evidence=adjacent,
            ),
        )


def _cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    if not a or len(a) != len(b) or not all(math.isfinite(x) for x in (*a, *b)):
        raise ValueError("invalid embedding dimensions or values")
    length = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / length if length else 0
