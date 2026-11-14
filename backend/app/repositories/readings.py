"""Local immutable-artifact store and transactional reading-version registry.

Only ingestion uses this repository directly. Student-facing access goes through the
scoped Retriever; raw source PDFs, page renders and parser JSON are admin-only.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path
from typing import Any

from app.ingestion.reading_models import ParsedReading, QualityReport


class ReadingRepository:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = self.root / "readings.sqlite3"
        with self.connect() as db:
            schema_version = db.execute("PRAGMA user_version").fetchone()[0]
            if schema_version > 1:
                raise ValueError("reading database schema is newer than this application")
            if schema_version == 0:
                db.executescript(
                    files("app.repositories").joinpath("sql/0001_readings.sql").read_text()
                )

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def version_directory(self, document_id: str, version: str) -> Path:
        # IDs from a catalogue must still never become path traversal.
        from hashlib import sha256

        key = sha256(document_id.encode()).hexdigest()[:24]
        if not version or any(c not in "0123456789abcdef" for c in version):
            raise ValueError("invalid version identifier")
        return self.root / key / version

    def existing(self, document_id: str, version: str) -> QualityReport | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT report_json FROM reading_versions WHERE document_id=? AND version=?",
                (document_id, version),
            ).fetchone()
        return QualityReport.model_validate_json(row["report_json"]) if row else None

    def publish(self, reading: ParsedReading, report: QualityReport, directory: Path) -> None:
        if (
            report.document_id != reading.document.document_id
            or report.ingestion_version != reading.ingestion_version
            or report.source_checksum != reading.source_checksum
        ):
            raise ValueError("report does not match parsed reading")
        relative = str(directory.resolve().relative_to(self.root))
        with self.connect() as db:
            db.execute(
                "INSERT INTO reading_versions VALUES (?,?,?,?,?,?,?)",
                (
                    reading.document.document_id,
                    reading.ingestion_version,
                    reading.document.course_id,
                    reading.document.title,
                    relative,
                    reading.model_dump_json(),
                    report.model_dump_json(),
                ),
            )
            if report.text_activatable and not report.errors:
                db.execute(
                    "INSERT INTO active_readings VALUES (?,?) "
                    "ON CONFLICT(document_id) DO UPDATE SET version=excluded.version",
                    (reading.document.document_id, reading.ingestion_version),
                )

    def active_candidates(
        self,
        course_id: str,
        document_ids: frozenset[str],
    ) -> list[tuple[ParsedReading, Path]]:
        if not document_ids:
            return []
        with self.connect() as db:
            rows = db.execute(
                "SELECT v.parsed_json, v.artifact_dir FROM reading_versions v "
                "JOIN active_readings a ON a.document_id=v.document_id AND a.version=v.version "
                "WHERE v.course_id=? AND v.document_id IN ("
                + ",".join("?" for _ in document_ids)
                + ")",
                (course_id, *sorted(document_ids)),
            ).fetchall()
        return [
            (
                ParsedReading.model_validate_json(row["parsed_json"]),
                self._artifact_path(row["artifact_dir"]),
            )
            for row in rows
        ]

    def _artifact_path(self, relative: str) -> Path:
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("artifact path escapes storage root")
        return path

    def inventory(self) -> list[dict[str, Any]]:
        """Admin/operator diagnostics only; contains no reading passages."""
        with self.connect() as db:
            rows = db.execute(
                "SELECT v.document_id,v.version,v.course_id,v.report_json,"
                "(a.version = v.version) AS active FROM reading_versions v "
                "LEFT JOIN active_readings a ON a.document_id=v.document_id "
                "ORDER BY v.course_id,v.version"
            ).fetchall()
        return [
            {
                "document_id": row["document_id"],
                "version": row["version"],
                "course_id": row["course_id"],
                "active": bool(row["active"]),
                "report": json.loads(row["report_json"]),
            }
            for row in rows
        ]
