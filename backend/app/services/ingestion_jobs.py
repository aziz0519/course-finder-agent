"""In-process development ingestion jobs behind the admin API."""

from __future__ import annotations

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
        try:
            dataset = load_dataset(self.data_root)
            reviews = load_reviews(self.data_root / "manifests" / "reading_qa.json")
            reports = []
            for document in dataset.catalog.reading_documents:
                report = ingest_reading(
                    document,
                    self.data_root / "samples" / "course-materials",
                    self.repository,
                    reviews.documents.get(document.document_id),
                )
                reports.append(report.model_dump(mode="json"))
            update: dict[str, object] = {
                "status": "completed",
                "report": {"documents": reports},
                "completed_at": datetime.now(UTC),
            }
        except Exception as exc:
            update = {
                "status": "failed",
                "report": {"error_type": type(exc).__name__},
                "completed_at": datetime.now(UTC),
            }
        with self._lock:
            self._jobs[job_id].update(update)
