"""Dataset loading: read the sources, preserve provenance, adapt, and enrich.

The returned objects are immutable and shared read-only across the request; nothing
here touches the network, the database, or a model provider.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.domain.catalog import AcademicCatalog
from app.domain.errors import DatasetError, UnknownStudentError
from app.domain.models import Program, ReadingDocument, Student
from app.ingestion.json_adapters import adapt_catalogue, adapt_students

CATALOGUE_PATH = Path("samples/course-catalog.json")
STUDENTS_PATH = Path("samples/student-records.json")
MANIFEST_PATH = Path("manifests/course_readings_manifest.json")


@dataclass(frozen=True)
class SourceDocument:
    """One supplied file, with the checksum that identifies its version."""

    path: Path
    sha256: str
    raw: Mapping[str, Any]

    @property
    def source_version(self) -> str:
        return self.sha256[:12]


@dataclass(frozen=True)
class AcademicDataset:
    """The authoritative academic state for one scenario load."""

    catalog: AcademicCatalog
    students: tuple[Student, ...]
    catalogue_source: SourceDocument
    students_source: SourceDocument

    def student(self, student_id: str) -> Student:
        for student in self.students:
            if student.student_id == student_id:
                return student
        raise UnknownStudentError(student_id)

    def program_for(self, student: Student) -> Program:
        return self.catalog.program(student.program_id)


def _read_source(path: Path) -> SourceDocument:
    if not path.is_file():
        raise DatasetError(f"missing source file: {path}")
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise DatasetError(f"cannot read {path}: {exc}") from exc

    try:
        raw = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DatasetError(f"{path} is not valid UTF-8 JSON: {exc}") from exc

    if not isinstance(raw, Mapping):
        raise DatasetError(f"{path}: expected a JSON object at the top level")

    return SourceDocument(
        path=path,
        sha256=hashlib.sha256(payload).hexdigest(),
        raw=raw,
    )


def _enrich_documents(catalog: AcademicCatalog, manifest_path: Path) -> AcademicCatalog:
    """Attach checksums and page counts from the reading manifest when it is present."""
    if not manifest_path.is_file():
        return catalog

    manifest = _read_source(manifest_path).raw
    entries: dict[tuple[str, str], Mapping[str, Any]] = {}
    for item in manifest.get("documents") or []:
        if not isinstance(item, Mapping):
            continue
        course_code = item.get("course_code")
        relative = item.get("relative_path")
        if isinstance(course_code, str) and isinstance(relative, str):
            entries[(course_code, Path(relative).name)] = item

    documents: list[ReadingDocument] = []
    for document in catalog.reading_documents:
        entry = entries.get((document.course_id, document.source_filename))
        if entry is None:
            documents.append(document)
            continue
        checksum = entry.get("sha256") or entry.get("expected_sha256")
        pages = entry.get("page_count") or entry.get("expected_page_count")
        documents.append(
            document.model_copy(
                update={
                    "file_checksum": checksum if isinstance(checksum, str) else None,
                    "page_count": pages if isinstance(pages, int) else None,
                }
            )
        )

    if all(
        original == enriched
        for original, enriched in zip(catalog.reading_documents, documents, strict=False)
    ):
        return catalog

    return AcademicCatalog(
        policy=catalog.policy,
        courses=catalog.courses,
        programs=catalog.programs,
        reading_documents=tuple(documents),
    )


def load_dataset(data_root: Path | None = None) -> AcademicDataset:
    """Load, validate, and index the supplied dataset.

    Raises ``DatasetError`` (or a more specific ``DomainError``) when the source is
    missing, malformed, or academically inconsistent.
    """
    root = (Path(data_root) if data_root is not None else get_settings().data_root).resolve()

    catalogue_source = _read_source(root / CATALOGUE_PATH)
    students_source = _read_source(root / STUDENTS_PATH)

    catalog = adapt_catalogue(catalogue_source.raw, dataset_root=root / "samples")
    catalog = _enrich_documents(catalog, root / MANIFEST_PATH)
    students = adapt_students(students_source.raw, catalog=catalog)

    return AcademicDataset(
        catalog=catalog,
        students=students,
        catalogue_source=catalogue_source,
        students_source=students_source,
    )
