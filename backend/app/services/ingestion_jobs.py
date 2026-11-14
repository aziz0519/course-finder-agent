"""In-process development ingestion jobs behind the admin API."""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.ingestion.dataset import load_dataset
from app.ingestion.readings import ingest_reading, load_reviews
from app.repositories.readings import ReadingRepository


class IngestionJobService:
    """Small local job registry; AWS replaces this with an isolated Fargate task."""

    def __init__(self, data_root: Path, repository: ReadingRepository):
        self.data_root = data_root
        self.repository = repository
        self._jobs: dict[str, dict[str, object]] = {}
        self._lock = threading.RLock()

    def create(self, dataset_version: str | None) -> dict[str, object]:
        job_id = f"ingestion-{uuid4()}"
        job: dict[str, object] = {
            "job_id": job_id,
            "dataset_version": dataset_version or "active-fixtures",
            "status": "queued",
            "report": None,
            "started_at": None,
            "completed_at": None,
        }
        with self._lock:
            self._jobs[job_id] = job
        return dict(job)

    def get(self, job_id: str) -> dict[str, object] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def run(self, job_id: str) -> None:
        started = datetime.now(UTC)
        with self._lock:
            self._jobs[job_id].update(status="running", started_at=started)
        reports = []
        document_id = None
        stage = "load_dataset"
        provenance: dict[str, object] = {}
        try:
            dataset = load_dataset(self.data_root)
            sources = {
                "catalogue": dataset.catalogue_source,
                "students": dataset.students_source,
            }
            version_data = {
                "sources": {name: source.sha256 for name, source in sources.items()},
                "documents": [d.model_dump(mode="json") for d in dataset.catalog.reading_documents],
            }
            verified_version = hashlib.sha256(
                json.dumps(version_data, sort_keys=True).encode()
            ).hexdigest()
            provenance = {"source_version": verified_version}
            with self._lock:
                requested_version = self._jobs[job_id]["dataset_version"]
                self._jobs[job_id]["dataset_version"] = verified_version
            stage = "resolve_version"
            if requested_version not in ("active-fixtures", verified_version):
                raise ValueError("unsupported dataset version")
            stage = "preserve_sources"
            # Administrator-only local audit artefact; never include raw JSON in status.
            audit_dir = self.repository.root / "jobs" / job_id
            audit_dir.mkdir(parents=True, exist_ok=True)
            (audit_dir / "sources.json").write_text(
                json.dumps(
                    {
                        "source_version": verified_version,
                        "sources": {
                            name: {
                                "path": str(source.path),
                                "sha256": source.sha256,
                                "version": source.source_version,
                                "raw": source.raw,
                            }
                            for name, source in sources.items()
                        },
                        "documents": version_data["documents"],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            stage = "load_reviews"
            reviews = load_reviews(self.data_root / "manifests" / "reading_qa.json")
            for document in dataset.catalog.reading_documents:
                document_id = document.document_id
                stage = "ingest_reading"
                report = ingest_reading(
                    document,
                    self.data_root / "samples" / "course-materials",
                    self.repository,
                    reviews.documents.get(document.document_id),
                )
                reports.append(report.model_dump(mode="json"))
            update: dict[str, object] = {
                "status": "completed",
                "report": {"documents": reports, **provenance},
                "completed_at": datetime.now(UTC),
            }
        except Exception as exc:
            update = {
                "status": "failed",
                "report": {
                    "documents": reports,
                    "error_type": type(exc).__name__,
                    "document_id": document_id,
                    "stage": stage,
                    **provenance,
                },
                "completed_at": datetime.now(UTC),
            }
        with self._lock:
            self._jobs[job_id].update(update)
