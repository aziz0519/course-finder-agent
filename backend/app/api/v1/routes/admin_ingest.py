"""Admin-only ingestion endpoints."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.api.v1.dependencies import AdminDep, CsrfAdminDep, ServicesDep
from app.schemas.ingestion import IngestionJobStart, IngestionJobStatus

router = APIRouter(prefix="/admin/ingestions", tags=["admin"])


@router.post("", response_model=IngestionJobStatus, status_code=status.HTTP_202_ACCEPTED)
def start_ingestion(
    payload: IngestionJobStart,
    background_tasks: BackgroundTasks,
    principal: CsrfAdminDep,
    services: ServicesDep,
) -> IngestionJobStatus:
    del principal
    job = services.ingestion_jobs.create(payload.dataset_version)
    background_tasks.add_task(services.ingestion_jobs.run, str(job["job_id"]))
    return IngestionJobStatus.model_validate(job)


@router.get("/{job_id}", response_model=IngestionJobStatus)
def get_ingestion(
    job_id: str,
    principal: AdminDep,
    services: ServicesDep,
) -> IngestionJobStatus:
    del principal
    job = services.ingestion_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return IngestionJobStatus.model_validate(job)
