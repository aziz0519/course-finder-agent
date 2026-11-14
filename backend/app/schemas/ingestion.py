"""Admin ingestion API contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class IngestionJobStart(BaseModel):
    dataset_version: str | None = None


class IngestionJobStatus(BaseModel):
    job_id: str
    dataset_version: str
    status: Literal["queued", "running", "completed", "failed"]
    report: dict[str, object] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
