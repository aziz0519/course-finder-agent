"""Native-first PDF extraction; no network calls, blanket OCR, or invented formulas."""

from __future__ import annotations

import hashlib
import json
import re
import time
from importlib.metadata import version
from pathlib import Path
from typing import Any, Protocol

import pdfplumber
import pymupdf

from app.domain.models import ReadingDocument
from app.ingestion.reading_models import (
    BBox,
    DocumentPage,
    DocumentReview,
    FigureAsset,
    ParsedReading,
    ReadingAttribution,
    ReadingChunk,
    RegionReview,
    SafetyLabel,
    VisualType,
)
from app.ingestion.safety import classify_page


class PdfParser(Protocol):
    @property
    def parser_id(self) -> str: ...

    def parse(
        self,
        source: Path,
        document: ReadingDocument,
        output: Path,
        ingestion_version: str,
        review: DocumentReview | None = None,
    ) -> ParsedReading: ...


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _bbox(value: Any) -> BBox:
    return (float(value[0]), float(value[1]), float(value[2]), float(value[3]))


def _overlap(a: BBox, b: BBox) -> bool:
    intersection = pymupdf.Rect(a) & pymupdf.Rect(b)
    return not intersection.is_empty and intersection.get_area() > 0.5 * min(
        pymupdf.Rect(a).get_area(), pymupdf.Rect(b).get_area()
    )


def _attribution(text: str) -> ReadingAttribution:
    # Preserve full attribution lines verbatim, not a model-generated credit.
    lines = text.splitlines()
    selected = [
        line
        for index, line in enumerate(lines)
        if any(
            word in line.lower()
            for word in (
                "creativecommons",
                "creative commons",
                "attribution",
                "wikipedia.org",
                "contributors",
                "sharealike",
            )
        )
        or (index > 0 and "creative commons" in lines[index - 1].lower())
    ]
    url = re.search(r"https?://creativecommons\.org/licenses/by-sa/[\d.]+/?", text)
    return ReadingAttribution(
        source_attribution="\n".join(selected),
        license_id="CC-BY-SA" if "sharealike" in text.lower() or url else None,
        license_url=url.group() if url else None,
    )


class NativePdfParser:
    """PyMuPDF placements/reading order + pdfplumber tables; uncertain visuals stay gated."""

    @property
    def parser_id(self) -> str:
        return f"native-v3:pymupdf-{version('pymupdf')}:pdfplumber-{version('pdfplumber')}"

    def parse(
        self,
        source: Path,
        document: ReadingDocument,
        output: Path,
        ingestion_version: str,
        review: DocumentReview | None = None,
    ) -> ParsedReading:
        started = time.monotonic()
        payload = source.read_bytes()
        checksum = sha256(payload)
        if document.file_checksum != checksum:
            raise ValueError(
                f"{document.document_id}: checksum mismatch or missing manifest checksum"
            )
        if review and review.source_checksum != checksum:
            raise ValueError("review checksum does not match source")
        output.mkdir(parents=True, exist_ok=True)
        (output / "assets").mkdir(exist_ok=True)
        (output / "pages").mkdir(exist_ok=True)
        (output / "layout").mkdir(exist_ok=True)
        pages: list[DocumentPage] = []
        chunks: list[ReadingChunk] = []
        assets: list[FigureAsset] = []
        with pymupdf.open(source) as pdf, pdfplumber.open(source) as tables:
            if pdf.is_encrypted:
                raise ValueError("encrypted PDFs are unsupported")
            if document.page_count != len(pdf):
                raise ValueError(f"{document.document_id}: page count differs from manifest")
            if review and (
                any(p < 1 or p > len(pdf) for p in review.text_pages)
                or any(r.page > len(pdf) for r in review.regions)
            ):
                raise ValueError("review references a nonexistent PDF page")
            for number, page in enumerate(pdf, start=1):
                text = page.get_text("text", sort=True)
                layout = page.get_text("dict", sort=True)
                # Embedded image bytes are separate binary artefacts, not JSON.
                for block in layout["blocks"]:
                    block.pop("image", None)
                    block.pop("mask", None)
                layout_uri = f"layout/{number:03d}.json"
                (output / layout_uri).write_text(json.dumps(layout), encoding="utf-8")
                page_uri = f"pages/{number:03d}.png"
                page.get_pixmap(dpi=110).save(output / page_uri)
                safety = classify_page(document.course_id, text)
                text_reviewed = review is not None and number in review.text_pages
                has_text = len(re.sub(r"\s", "", text)) >= 30 and "\ufffd" not in text
                flags: list[str] = []
                if not has_text:
                    flags.append(
                        "ocr_required" if page.get_image_info() else "text_layer_uncertain"
                    )
                if not text_reviewed:
                    flags.append("text_needs_review")
                if safety == "restricted":
                    flags.append("restricted_page")
                regions: list[tuple[BBox, VisualType, tuple[tuple[str | None, ...], ...]]] = []
                # get_image_info reports actual placements, unlike shared image resources.
                for image in page.get_image_info(xrefs=True):
                    box = _bbox(image["bbox"])
                    if pymupdf.Rect(box).get_area() > 60:
                        regions.append((box, "figure", ()))
                for table in tables.pages[number - 1].find_tables():
                    rows = tuple(tuple(cell for cell in row) for row in table.extract())
                    regions.append((_bbox(table.bbox), "table", rows))
                # Vector diagrams have no image XObject. Retain drawing clusters too.
                for rect in page.cluster_drawings():
                    box = _bbox(rect)
                    if (
                        rect.width > 35
                        and rect.height > 25
                        and not any(_overlap(box, existing[0]) for existing in regions)
                    ):
                        regions.append((box, "figure", ()))
                # Detect suspect displayed math; never claim native extraction is LaTeX.
                for block in layout["blocks"]:
                    if block["type"] != 0:
                        continue
                    spans = [s for line in block["lines"] for s in line["spans"]]
                    if any(
                        re.search(r"[∑∫√≈∝∞ℏ]", s["text"])
                        or "math" in s["font"].lower()
                        or "symbol" in s["font"].lower()
                        for s in spans
                    ):
                        box = _bbox(block["bbox"])
                        if not any(_overlap(box, r[0]) for r in regions):
                            regions.append((box, "equation", ()))
                annotations = [r for r in review.regions if r.page == number] if review else []
                # Reviewed regions override overlapping automatic detections.
                for annotation in annotations:
                    existing_rows = next(
                        (r[2] for r in regions if _overlap(r[0], annotation.bbox)), ()
                    )
                    regions = [r for r in regions if not _overlap(r[0], annotation.bbox)]
                    regions.append((annotation.bbox, annotation.visual_type, existing_rows))
                page_assets: list[FigureAsset] = []
                for index, (box, visual_type, rows) in enumerate(regions):
                    matched_review = next((r for r in annotations if r.bbox == box), None)
                    asset = self._asset(
                        page,
                        output,
                        document,
                        checksum,
                        ingestion_version,
                        number,
                        index,
                        box,
                        visual_type,
                        rows,
                        matched_review,
                        safety,
                    )
                    page_assets.append(asset)
                    flags.extend(asset.warnings)
                assets.extend(page_assets)
                for asset in page_assets:
                    if asset.visual_type != "table" or not asset.structured_rows:
                        continue
                    header, *body = asset.structured_rows
                    for start in range(0, len(body), 5):
                        row_group = (header, *body[start : start + 5])
                        table_text = "\n".join(
                            " | ".join(cell or "" for cell in row) for row in row_group
                        )
                        chunks.append(
                            ReadingChunk(
                                document_id=document.document_id,
                                course_id=document.course_id,
                                source_checksum=checksum,
                                ingestion_version=ingestion_version,
                                pdf_page_number=number,
                                printed_page_label=page.get_label() or None,
                                bbox=asset.bbox,
                                extraction_method="pdfplumber.table.row_group",
                                chunk_id=f"{asset.asset_id}:rows{start}",
                                section_path=(),
                                content_type="table",
                                text=table_text,
                                extraction_confidence=(
                                    0.95 if asset.review_status == "approved" else 0.4
                                ),
                                safety_label=safety,
                                text_reviewed=text_reviewed and asset.review_status == "approved",
                                asset_refs=(asset.asset_id,),
                            )
                        )
                section: tuple[str, ...] = ()
                for index, block in enumerate(layout["blocks"]):
                    if block["type"] != 0:
                        continue
                    block_text = "\n".join(
                        "".join(span["text"] for span in line["spans"]) for line in block["lines"]
                    ).strip()
                    if not block_text:
                        continue
                    box = _bbox(pymupdf.Rect(block["bbox"]) & page.rect)
                    spans = [s for line in block["lines"] for s in line["spans"]]
                    # Keep paragraph blocks intact; short large-font blocks are headings.
                    if len(block_text) < 100 and spans and max(s["size"] for s in spans) > 14:
                        section = (block_text,)
                    related = tuple(a.asset_id for a in page_assets if _overlap(box, a.bbox))
                    if re.match(r"Figure\s+\d+[.:]", block_text):
                        nearest = sorted(
                            (a for a in page_assets if a.visual_type in ("figure", "chart")),
                            key=lambda a: abs(box[1] - a.bbox[3]),
                        )
                        if not nearest or nearest[0].review_status != "approved":
                            continue
                        related = (nearest[0].asset_id,)
                        # Reviewed source captions are evidence linked to the original crop.
                        chunks.append(
                            ReadingChunk(
                                document_id=document.document_id,
                                course_id=document.course_id,
                                source_checksum=checksum,
                                ingestion_version=ingestion_version,
                                pdf_page_number=number,
                                printed_page_label=page.get_label() or None,
                                bbox=box,
                                extraction_method="pymupdf.native.caption",
                                chunk_id=f"{document.document_id}:{ingestion_version}:p{number}:b{index}",
                                section_path=section,
                                text=block_text,
                                content_type="caption",
                                extraction_confidence=0.95 if has_text else 0.2,
                                safety_label=safety,
                                text_reviewed=text_reviewed and has_text,
                                asset_refs=related,
                            )
                        )
                        continue
                    # Other visual text is not prose evidence.
                    if related:
                        continue
                    chunks.append(
                        ReadingChunk(
                            document_id=document.document_id,
                            course_id=document.course_id,
                            source_checksum=checksum,
                            ingestion_version=ingestion_version,
                            pdf_page_number=number,
                            printed_page_label=page.get_label() or None,
                            bbox=box,
                            extraction_method="pymupdf.native.blocks",
                            chunk_id=f"{document.document_id}:{ingestion_version}:p{number}:b{index}",
                            section_path=section,
                            text=block_text,
                            extraction_confidence=0.95 if has_text else 0.2,
                            safety_label=safety,
                            text_reviewed=text_reviewed and has_text,
                        )
                    )
                pages.append(
                    DocumentPage(
                        pdf_page_number=number,
                        printed_page_label=page.get_label() or None,
                        width=page.rect.width,
                        height=page.rect.height,
                        rotation=page.rotation,
                        has_text_layer=has_text,
                        status="native_text"
                        if has_text
                        else ("image_only" if page.get_image_info() else "extraction_failure"),
                        page_image_uri=page_uri,
                        extracted_text=text,
                        text_reviewed=text_reviewed and has_text,
                        safety_label=safety,
                        quality_flags=tuple(sorted(set(flags))),
                        layout_json=layout_uri,
                    )
                )
            result = ParsedReading(
                document=document.model_copy(update={"ingestion_version": ingestion_version}),
                source_checksum=checksum,
                ingestion_version=ingestion_version,
                parser_id=self.parser_id,
                parser_versions={
                    "pymupdf": version("pymupdf"),
                    "pdfplumber": version("pdfplumber"),
                },
                parser_options={
                    "render_dpi": "110",
                    "crop_dpi": "144",
                    "ocr": "targeted-needed-only",
                    "vlm": "disabled",
                    "safety_policy": "conservative-page-v1",
                },
                source_size_bytes=len(payload),
                source_metadata=pdf.metadata,
                outline=tuple(tuple(item) for item in pdf.get_toc()),
                encrypted=False,
                pages=tuple(pages),
                chunks=tuple(chunks),
                assets=tuple(assets),
                attribution=_attribution("\n".join(p.extracted_text for p in pages)),
                processing_seconds=time.monotonic() - started,
            )
        (output / "source.pdf").write_bytes(payload)
        (output / "parsed.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
        self._contact_sheet(output, pages)
        return result

    @staticmethod
    def _asset(
        page: Any,
        output: Path,
        document: ReadingDocument,
        checksum: str,
        ingestion_version: str,
        number: int,
        index: int,
        box: BBox,
        visual_type: VisualType,
        rows: tuple[tuple[str | None, ...], ...],
        annotation: RegionReview | None,
        safety: SafetyLabel,
    ) -> FigureAsset:
        rect = pymupdf.Rect(box)
        if rect.is_empty or not page.rect.contains(rect):
            raise ValueError(f"invalid visual region on page {number}")
        payload = page.get_pixmap(clip=rect, dpi=144).tobytes("png")
        digest = sha256(payload)
        uri = f"assets/{digest}.png"
        if not (output / uri).exists():
            (output / uri).write_bytes(payload)
        warnings: list[str] = []
        if not annotation or not annotation.caption:
            warnings.append("caption_missing")
        if not annotation or annotation.status != "approved":
            warnings.append(f"{visual_type}_needs_review")
        if visual_type == "equation" and (not annotation or not annotation.latex):
            warnings.append("equation_unparsed")
        return FigureAsset(
            document_id=document.document_id,
            course_id=document.course_id,
            source_checksum=checksum,
            ingestion_version=ingestion_version,
            pdf_page_number=number,
            printed_page_label=page.get_label() or None,
            bbox=box,
            extraction_method="pdfplumber.table" if rows else "pymupdf.region",
            asset_id=f"{document.document_id}:{ingestion_version}:p{number}:a{index}",
            asset_uri=uri,
            sha256=digest,
            visual_type=visual_type,
            caption=annotation.caption if annotation else None,
            source_transcription=annotation.source_transcription if annotation else None,
            label=annotation.label if annotation else None,
            review_status=annotation.status if annotation else "needs_review",
            safety_label=safety,
            structured_rows=rows,
            latex=annotation.latex if annotation else None,
            exact_values_verified=annotation.exact_values_verified if annotation else False,
            warnings=tuple(warnings),
        )

    @staticmethod
    def _contact_sheet(output: Path, pages: list[DocumentPage]) -> None:
        sheet = pymupdf.open()
        for start in range(0, len(pages), 6):
            canvas = sheet.new_page(width=900, height=850)
            for index, page in enumerate(pages[start : start + 6]):
                col, row = index % 3, index // 3
                rect = pymupdf.Rect(col * 300, row * 425 + 20, col * 300 + 298, row * 425 + 420)
                canvas.insert_image(rect, filename=str(output / page.page_image_uri))
                canvas.insert_text(
                    (col * 300 + 8, row * 425 + 14), f"PDF page {page.pdf_page_number}", fontsize=10
                )
            canvas.get_pixmap().save(output / f"contact-sheet-{start // 6 + 1}.png")
        sheet.close()
