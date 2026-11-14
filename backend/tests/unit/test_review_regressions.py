import json
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.api.v1.routes.academic_plan import get_academic_plan
from app.api.v1.routes.courses import get_course
from app.api.v1.services import ApiServices
from app.auth.local_adapter import Principal
from app.core.config import Settings
from app.schemas.academic_plan import PlanQuery
from app.schemas.chat import MessageCreate
from app.services.ingestion_jobs import IngestionJobService


@pytest.mark.parametrize("content", ["", " ", "\t\n", "\u2003"])
def test_blank_messages_rejected(content):
    with pytest.raises(ValidationError):
        MessageCreate(content=content)


def test_nonblank_content_preserved():
    assert MessageCreate(content="  hello\n").content == "  hello\n"


def test_plan_loads_dataset_once(dataset):
    services = Mock()
    services.dataset.side_effect = [dataset, AssertionError("second dataset load")]
    principal = Principal(user_id="u", username="s", role="student", student_id="student-001")
    assert get_academic_plan(PlanQuery(), principal, services).student_id == "student-001"
    services.dataset.assert_called_once()


def test_course_exact_lookup_precedes_uppercase(dataset):
    services = Mock()
    course = dataset.catalog.courses[0].model_copy(update={"course_id": "Mixed"})
    services.dataset.return_value.catalog.maybe_course.side_effect = [course]
    assert get_course("Mixed", Mock(), services).course_id == "Mixed"
    services.dataset.return_value.catalog.maybe_course.assert_called_once_with("Mixed")
    services.dataset.return_value.catalog.maybe_course.reset_mock(side_effect=True)
    services.dataset.return_value.catalog.maybe_course.side_effect = [None, course]
    assert get_course("mixed", Mock(), services).course_id == "Mixed"
    assert services.dataset.return_value.catalog.maybe_course.call_args_list == [
        (("mixed",),),
        (("MIXED",),),
    ]


def test_cognito_fails_closed_before_local_auth(tmp_path):
    with pytest.raises(RuntimeError, match="Cognito authentication is disabled"):
        ApiServices.create(Settings(data_root=tmp_path, auth_provider="cognito"))
    assert not (tmp_path / "processed").exists()


def test_job_rejects_unknown_version_before_ingestion(data_root, tmp_path, monkeypatch):
    repository = Mock(root=tmp_path)
    ingest = Mock()
    monkeypatch.setattr("app.services.ingestion_jobs.ingest_reading", ingest)
    service = IngestionJobService(data_root, repository)
    job_id = str(service.create("invented-version")["job_id"])
    service.run(job_id)
    job = service.get(job_id)
    assert job is not None
    status_report = job["report"]
    assert isinstance(status_report, dict)
    assert job["status"] == "failed"
    assert status_report["stage"] == "resolve_version"
    assert job["dataset_version"] != "invented-version"
    ingest.assert_not_called()


def test_failed_job_preserves_reports_and_source_audit(data_root, dataset, tmp_path, monkeypatch):
    report = Mock()
    report.model_dump.return_value = {"quality": "retained"}
    ingest = Mock(side_effect=[report, RuntimeError("secret source text")])
    monkeypatch.setattr("app.services.ingestion_jobs.ingest_reading", ingest)
    service = IngestionJobService(data_root, Mock(root=tmp_path))
    job_id = str(service.create(None)["job_id"])
    service.run(job_id)
    job = service.get(job_id)
    assert job is not None
    status_report = job["report"]
    assert isinstance(status_report, dict)
    assert job["status"] == "failed"
    assert status_report["documents"] == [{"quality": "retained"}]
    assert status_report["document_id"] == dataset.catalog.reading_documents[1].document_id
    assert status_report["stage"] == "ingest_reading"
    assert "secret source text" not in str(job)
    audit = json.loads((tmp_path / "jobs" / job_id / "sources.json").read_text())
    assert audit["sources"]["catalogue"]["raw"] == dataset.catalogue_source.raw
    assert audit["sources"]["catalogue"]["sha256"] == dataset.catalogue_source.sha256
    assert job["dataset_version"] == audit["source_version"]
