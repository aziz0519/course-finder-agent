"""Owner-scoped citation and visual-asset responses."""

from __future__ import annotations

from pydantic import BaseModel


class CitationEvidenceResponse(BaseModel):
    document_title: str
    document_id: str
    course_code: str
    page_number: int
    section: tuple[str, ...]
    excerpt: str
    chunk_id: str
    source_checksum: str
    ingestion_version: str
    extraction_method: str
