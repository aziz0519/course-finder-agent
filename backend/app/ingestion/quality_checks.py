"""Structural QA is automatic; visual/text review is explicit and checksum-bound."""

from pathlib import Path

import pymupdf

from app.ingestion.pdf_pipeline import sha256
from app.ingestion.reading_models import FigureAsset, ParsedReading, QualityReport, ReadingChunk


def check_reading(reading: ParsedReading, root: Path) -> QualityReport:
    errors: list[str] = []
    warnings: list[str] = []
    expected = reading.document.page_count
    if reading.document.file_checksum != reading.source_checksum:
        errors.append("source_checksum_mismatch")
    if (
        not _exists(root, "source.pdf")
        or sha256((root / "source.pdf").read_bytes()) != reading.source_checksum
    ):
        errors.append("source_integrity_failure")
    if [p.pdf_page_number for p in reading.pages] != list(range(1, (expected or 0) + 1)):
        errors.append("page_coverage_mismatch")
    pages = {p.pdf_page_number: p for p in reading.pages}
    chunk_ids = [c.chunk_id for c in reading.chunks]
    asset_ids = [a.asset_id for a in reading.assets]
    assets_by_id = {a.asset_id: a for a in reading.assets}
    if len(set(chunk_ids)) != len(chunk_ids) or len(set(asset_ids)) != len(asset_ids):
        errors.append("duplicate_record_id")
    for page in reading.pages:
        for uri in (page.page_image_uri, page.layout_json):
            if not _exists(root, uri):
                errors.append(f"missing_page_artifact:p{page.pdf_page_number}")
        if page.status == "extraction_failure":
            warnings.append(f"extraction_failure:p{page.pdf_page_number}")
        warnings.extend(f"p{page.pdf_page_number}:{flag}" for flag in page.quality_flags)
    records: list[ReadingChunk | FigureAsset] = [*reading.chunks, *reading.assets]
    for record in records:
        source_page = pages.get(record.pdf_page_number)
        if (
            source_page is None
            or record.document_id != reading.document.document_id
            or record.course_id != reading.document.course_id
            or record.source_checksum != reading.source_checksum
            or record.ingestion_version != reading.ingestion_version
        ):
            errors.append("record_provenance_mismatch")
            continue
        rect = pymupdf.Rect(record.bbox)
        if rect.is_empty or not pymupdf.Rect(0, 0, source_page.width, source_page.height).contains(
            rect
        ):
            errors.append("record_bbox_invalid")
        if record.safety_label != source_page.safety_label:
            errors.append("record_safety_mismatch")
    for chunk in reading.chunks:
        if not set(chunk.asset_refs) <= set(asset_ids):
            errors.append("dangling_asset_reference")
        if (
            chunk.text_reviewed
            and chunk.asset_refs
            and any(
                assets_by_id[ref].review_status != "approved"
                or assets_by_id[ref].safety_label != chunk.safety_label
                for ref in chunk.asset_refs
                if ref in assets_by_id
            )
        ):
            errors.append("chunk_asset_review_mismatch")
        if chunk.text_reviewed and (
            chunk.pdf_page_number not in pages or not pages[chunk.pdf_page_number].text_reviewed
        ):
            errors.append("chunk_review_mismatch")
    for asset in reading.assets:
        if not _exists(root, asset.asset_uri):
            errors.append("missing_asset")
        elif sha256((root / asset.asset_uri).read_bytes()) != asset.sha256:
            errors.append("asset_checksum_mismatch")
        if asset.review_status != "approved":
            warnings.append(f"p{asset.pdf_page_number}:{asset.visual_type}_needs_review")
        if asset.visual_type == "table" and not asset.structured_rows:
            warnings.append(f"p{asset.pdf_page_number}:table_unparsed")
        if asset.visual_type == "table" and asset.exact_values_verified:
            rows = asset.structured_rows
            if len(rows) < 2 or any(len(row) != len(rows[0]) for row in rows):
                errors.append("verified_table_structure_invalid")
    return QualityReport(
        document_id=reading.document.document_id,
        source_checksum=reading.source_checksum,
        ingestion_version=reading.ingestion_version,
        page_count=len(reading.pages),
        chunk_count=len(reading.chunks),
        asset_count=len(reading.assets),
        reviewed_text_pages=sum(p.text_reviewed for p in reading.pages),
        approved_assets=sum(a.review_status == "approved" for a in reading.assets),
        restricted_chunks=sum(c.safety_label == "restricted" for c in reading.chunks),
        text_activatable=not errors
        and any(c.text_reviewed and c.extraction_confidence >= 0.8 for c in reading.chunks),
        visual_qa_complete=not errors
        and all(p.text_reviewed for p in reading.pages)
        and all(a.review_status == "approved" for a in reading.assets),
        errors=tuple(sorted(set(errors))),
        warnings=tuple(sorted(set(warnings))),
        parser_versions=reading.parser_versions,
        processing_seconds=reading.processing_seconds,
    )


def _exists(root: Path, relative: str) -> bool:
    path = (root / relative).resolve()
    return path.is_relative_to(root.resolve()) and path.is_file()
