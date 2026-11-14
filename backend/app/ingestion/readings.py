"""Repeatable local ingestion. A reviewed source/version is never overwritten."""

from __future__ import annotations

import errno
import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

from app.domain.models import ReadingDocument
from app.ingestion.pdf_pipeline import NativePdfParser, PdfParser, sha256
from app.ingestion.quality_checks import check_reading
from app.ingestion.reading_models import (
    DocumentReview,
    ParsedReading,
    QualityReport,
    ReviewManifest,
)
from app.repositories.readings import ReadingRepository


def load_reviews(path: Path) -> ReviewManifest:
    return ReviewManifest.model_validate_json(path.read_text(encoding="utf-8"))


def ingest_reading(
    document: ReadingDocument,
    samples: Path,
    repository: ReadingRepository,
    review: DocumentReview | None = None,
    parser: PdfParser | None = None,
) -> QualityReport:
    parser = parser or NativePdfParser()
    root = samples.resolve()
    source = (root / document.source_filename).resolve()
    if not source.is_relative_to(root) or source.suffix.lower() != ".pdf":
        raise ValueError("source must be a PDF inside the dataset root")
    if not source.is_file() or source.stat().st_size > 50 * 1024 * 1024:
        raise ValueError("source missing or exceeds 50 MiB")
    if not source.read_bytes().startswith(b"%PDF-"):
        raise ValueError("source is not a PDF")
    checksum = sha256(source.read_bytes())
    if document.file_checksum != checksum:
        raise ValueError(f"{document.document_id}: source checksum mismatch")
    if review and review.source_checksum != checksum:
        raise ValueError("stale review: source checksum differs")
    version_key = json.dumps(
        {
            "source": checksum,
            "document": document.model_dump(mode="json"),
            "parser": parser.parser_id,
            "pipeline": "reading-v1:safety-page-v1",
            "review": review.model_dump(mode="json") if review else None,
        },
        sort_keys=True,
    ).encode()
    ingestion_version = sha256(version_key)[:24]
    existing = repository.existing(document.document_id, ingestion_version)
    if existing:
        return existing
    directory = repository.version_directory(document.document_id, ingestion_version)
    directory.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=directory.parent))
    try:
        parsed = parser.parse(source, document, staging, ingestion_version, review)
        (staging / "parsed.json").write_text(parsed.model_dump_json(indent=2), encoding="utf-8")
        report = check_reading(parsed, staging)
        (staging / "quality.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
        if not directory.exists():
            try:
                os.replace(staging, directory)
            except OSError as exc:
                if exc.errno not in (errno.EEXIST, errno.ENOTEMPTY) or not directory.is_dir():
                    raise
        if directory.exists():
            # Recover an artefact-complete job interrupted before its registry commit.
            previous = ParsedReading.model_validate_json((directory / "parsed.json").read_text())
            if (
                previous.ingestion_version != ingestion_version
                or previous.source_checksum != checksum
                or previous.document
                != document.model_copy(update={"ingestion_version": ingestion_version})
            ):
                raise ValueError("existing immutable version conflicts")
            parsed = previous
            report = check_reading(parsed, directory)
        try:
            repository.publish(parsed, report, directory)
        except sqlite3.IntegrityError as exc:
            if getattr(exc, "sqlite_errorcode", None) not in (
                sqlite3.SQLITE_CONSTRAINT_PRIMARYKEY,
                sqlite3.SQLITE_CONSTRAINT_UNIQUE,
            ) or str(exc) != (
                "UNIQUE constraint failed: reading_versions.document_id, reading_versions.version"
            ):
                raise
            committed = repository.existing(document.document_id, ingestion_version)
            if committed is None or committed.source_checksum != checksum:
                raise
            return committed
        return report
    except Exception as exc:
        # Keep diagnostics but never activate an incomplete/failed extraction.
        if staging.exists():
            (staging / "failure.json").write_text(
                json.dumps({"error_type": type(exc).__name__, "version": ingestion_version}),
                encoding="utf-8",
            )
        raise
    finally:
        if (
            staging.exists()
            and (staging / "quality.json").exists()
            and not (staging / "failure.json").exists()
        ):
            shutil.rmtree(staging)
