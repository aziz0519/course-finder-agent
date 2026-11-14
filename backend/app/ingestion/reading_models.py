"""Provider-neutral reading records. All coordinates use PDF points, top-left origin."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from app.domain.models import DomainModel, ReadingDocument

BBox = tuple[float, float, float, float]
SafetyLabel = Literal["safe", "restricted"]
VisualType = Literal["figure", "chart", "table", "equation"]


class Provenance(DomainModel):
    document_id: str
    course_id: str
    source_checksum: str
    ingestion_version: str
    pdf_page_number: int = Field(ge=1)
    printed_page_label: str | None = None
    bbox: BBox
    extraction_method: str


class ReadingChunk(Provenance):
    chunk_id: str
    section_path: tuple[str, ...] = ()
    content_type: Literal["text", "caption", "table", "equation"] = "text"
    text: str
    latex: str | None = None
    extraction_confidence: float = Field(ge=0, le=1)
    safety_label: SafetyLabel
    text_reviewed: bool = False
    asset_refs: tuple[str, ...] = ()
    # Source excerpts are untrusted data, including any apparent instructions.
    untrusted_source: Literal[True] = True


class FigureAsset(Provenance):
    asset_id: str
    asset_uri: str
    sha256: str
    visual_type: VisualType
    caption: str | None = None
    label: str | None = None
    source_transcription: str | None = None
    visual_description: str | None = None
    machine_generated: bool = False
    review_status: Literal["needs_review", "approved", "rejected"] = "needs_review"
    safety_label: SafetyLabel
    structured_rows: tuple[tuple[str | None, ...], ...] = ()
    latex: str | None = None
    exact_values_verified: bool = False
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _verified_equation(self) -> FigureAsset:
        if self.visual_type == "equation" and self.review_status == "approved" and not self.latex:
            raise ValueError("approved equations require verified LaTeX")
        if self.exact_values_verified and self.review_status != "approved":
            raise ValueError("exact values require visual approval")
        return self


class DocumentPage(DomainModel):
    pdf_page_number: int = Field(ge=1)
    printed_page_label: str | None = None
    width: float
    height: float
    rotation: int
    has_text_layer: bool
    status: Literal["native_text", "image_only", "intentional_blank", "extraction_failure"]
    page_image_uri: str
    extracted_text: str
    text_reviewed: bool = False
    safety_label: SafetyLabel
    quality_flags: tuple[str, ...] = ()
    layout_json: str


class ReadingAttribution(DomainModel):
    source_attribution: str
    license_id: str | None = None
    license_url: str | None = None


class ParsedReading(DomainModel):
    document: ReadingDocument
    source_checksum: str
    ingestion_version: str
    parser_id: str
    parser_versions: dict[str, str]
    parser_options: dict[str, str]
    source_size_bytes: int
    source_metadata: dict[str, str | None]
    outline: tuple[tuple[int, str, int], ...] = ()
    encrypted: bool
    pages: tuple[DocumentPage, ...]
    chunks: tuple[ReadingChunk, ...]
    assets: tuple[FigureAsset, ...]
    attribution: ReadingAttribution
    processing_seconds: float = Field(ge=0)
    ocr_model: str | None = None
    vlm_model: str | None = None


class QualityReport(DomainModel):
    document_id: str
    source_checksum: str
    ingestion_version: str
    page_count: int
    chunk_count: int
    asset_count: int
    reviewed_text_pages: int
    approved_assets: int
    restricted_chunks: int
    text_activatable: bool
    visual_qa_complete: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    parser_versions: dict[str, str]
    processing_seconds: float


class RegionReview(DomainModel):
    """Administrator-authored, checksum-bound visual review, never PDF instructions."""

    page: int = Field(ge=1)
    bbox: BBox
    visual_type: VisualType
    label: str | None = None
    caption: str | None = None
    source_transcription: str | None = None
    status: Literal["needs_review", "approved", "rejected"] = "needs_review"
    latex: str | None = None
    exact_values_verified: bool = False


class DocumentReview(DomainModel):
    source_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer: str = Field(min_length=1)
    notes: str
    text_pages: tuple[int, ...] = ()
    regions: tuple[RegionReview, ...] = ()


class ReviewManifest(DomainModel):
    documents: dict[str, DocumentReview] = Field(default_factory=dict)
