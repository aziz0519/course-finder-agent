"""HTTP-level tests for the M5 UI controller (real API, no browser)."""

from __future__ import annotations

import shutil
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi import FastAPI
from pydantic import SecretStr
from ui.api_client import ApiClient, ApiError, SessionState

from app.core.config import Settings
from app.ingestion.readings import ingest_reading, load_reviews
from app.main import create_app

PASSWORD = "test-password"


@pytest.fixture
def api_app(data_root: Path, tmp_path: Path) -> FastAPI:
    isolated = tmp_path / "data"
    shutil.copytree(data_root / "samples", isolated / "samples")
    shutil.copytree(data_root / "manifests", isolated / "manifests")
    settings = Settings(
        app_env="test",
        data_root=isolated,
        local_dev_password=SecretStr(PASSWORD),
        session_secret=SecretStr("test-session-secret"),
        csrf_secret=SecretStr("test-csrf-secret"),
    )
    return create_app(settings)


@pytest.fixture
def api_url(api_app: FastAPI) -> Iterator[str]:
    """Run the real ASGI app so cookies, CSRF, and middleware are exercised."""

    config = uvicorn.Config(
        api_app,
        host="127.0.0.1",
        port=0,
        log_level="error",
        lifespan="on",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    if not server.started:
        raise RuntimeError("test API server did not start")
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=15)


@pytest.fixture
def client(api_url: str) -> ApiClient:
    return ApiClient(base_url=api_url, timeout=10.0)


def _as(client: ApiClient, state: SessionState) -> ApiClient:
    return ApiClient.from_session(
        state,
        base_url=client.base_url,
        transport=client.transport,
    )


def _ingest_bohr(app: FastAPI) -> None:
    services = app.state.services
    document = services.dataset().catalog.document("phys350-bohr-model")
    assert document is not None
    reviews = load_reviews(services.settings.manifests_dir / "reading_qa.json")
    ingest_reading(
        document,
        services.settings.course_materials_dir,
        services.readings,
        reviews.documents[document.document_id],
    )


def test_ui_client_login_dashboard_and_plan(client: ApiClient) -> None:
    state = client.login("student-001", PASSWORD)
    assert state.role == "student"
    assert state.student_id == "student-001"
    assert state.cookie

    student = _as(client, state)
    assert student.profile()["student_id"] == "student-001"
    assert {course["course_code"] for course in student.profile()["current_courses"]} == {
        "PHYS 350",
        "HIST 210",
        "ENGL 120",
    }
    assert student.materials()["courses"]
    assert student.progress()["requirement_groups"]

    twelve = student.plan(unit_cap=12)
    assert twelve["plan"]["total_units"] == 12
    eight = student.plan(unit_cap=8)
    assert eight["plan"]["total_units"] == 8
    assert eight["plan"]["catalogue_max_units"] == 16


def test_ui_client_rejects_bad_credentials_and_invalid_session(client: ApiClient) -> None:
    with pytest.raises(ApiError) as bad_login:
        client.login("student-001", "wrong")
    assert bad_login.value.status_code == 401

    forged = SessionState(
        user_id="user-student-001",
        role="student",
        student_id="student-001",
        adviser_id=None,
        csrf_token="forged",
        cookie="forged",
    )
    with pytest.raises(ApiError) as expired:
        _as(client, forged).profile()
    assert expired.value.status_code == 401


@pytest.mark.corpus
def test_ui_client_chat_citations_and_page_images(
    api_app: FastAPI,
    client: ApiClient,
) -> None:
    _ingest_bohr(api_app)
    student = _as(client, client.login("student-001", PASSWORD))
    thread_id = student.create_thread()["thread_id"]

    answer = student.send(
        thread_id, "How does the Bohr model explain the hydrogen spectrum?"
    )["response"]
    assert answer["citations"]
    citation = answer["citations"][0]

    evidence = student.citation(thread_id, citation["chunk_id"])
    assert evidence["document_title"] == "Bohr model"
    assert evidence["page_number"] == citation["pdf_page_number"]

    page = student.page_bytes(
        thread_id, evidence["document_id"], evidence["page_number"]
    )
    assert page.startswith(b"\x89PNG")

    visual = student.send(
        thread_id,
        "I mean Figure 2. How many electrons can the second energy level hold?",
    )["response"]
    assert visual["citations"]
    asset = visual["citations"][0]["asset_id"]
    assert asset
    assert student.asset_bytes(thread_id, asset).startswith(b"\x89PNG")


@pytest.mark.corpus
def test_ui_client_owner_scope_and_adviser_assignment(
    api_app: FastAPI,
    client: ApiClient,
) -> None:
    _ingest_bohr(api_app)
    owner = _as(client, client.login("student-001", PASSWORD))
    thread_id = owner.create_thread()["thread_id"]
    owner.send(thread_id, "Explain the Bohr model.")
    other = _as(client, client.login("student-002", PASSWORD))
    with pytest.raises(ApiError) as denied:
        other.thread(thread_id)
    assert denied.value.status_code == 404

    adviser = _as(client, client.login("adviser-001", PASSWORD))
    assigned = adviser.assigned_students()
    assert [item["student_id"] for item in assigned] == ["student-001"]
    assert adviser.assigned_student("student-001")["student"]["student_id"] == "student-001"
    with pytest.raises(ApiError) as wrong_scope:
        adviser.assigned_student("student-002")
    assert wrong_scope.value.status_code == 404

    with pytest.raises(ApiError) as student_only:
        owner.assigned_students()
    assert student_only.value.status_code == 403


def test_ui_client_admin_ingestion_is_role_gated(
    api_app: FastAPI,
    client: ApiClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = api_app.state.services
    monkeypatch.setattr(services.ingestion_jobs, "run", lambda job_id: None)

    admin = _as(client, client.login("admin", PASSWORD))
    job = admin.start_ingestion()
    assert job["status"] == "queued"
    assert admin.ingestion(job["job_id"])["job_id"] == job["job_id"]

    student = _as(client, client.login("student-001", PASSWORD))
    with pytest.raises(ApiError) as denied:
        student.start_ingestion()
    assert denied.value.status_code == 403


def _panels(result: tuple[object, ...], keys: tuple[str, ...]) -> dict[str, Any]:
    return dict(zip(keys, result[6:], strict=True))


def test_login_and_logout_reset_every_user_panel(
    api_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One browser tab must never show the previous user's transcript or plans."""

    monkeypatch.setenv("COURSE_FINDER_API_URL", api_url)
    from ui import app as ui_app

    state, *rest = ui_app._login("student-001", PASSWORD)
    assert isinstance(state, SessionState)
    assert state.role == "student"
    assert rest[0]["visible"] is False
    assert rest[1]["visible"] is True
    assert rest[4] == ""

    panels = _panels((state, *rest), ui_app.PANEL_RESET_KEYS)
    assert panels["chatbot"] == []
    assert panels["thread_id"] == ""
    assert panels["citations"] == []
    assert panels["citation_picker"]["choices"] == []
    assert panels["citation_detail"] == ui_app.CITATION_HINT
    assert panels["page_view"] is None
    assert panels["asset_view"] is None
    assert panels["message"] == ""
    assert panels["adviser_students"]["choices"] == []
    assert panels["plan_table"] == []
    assert panels["job_id"] == ""
    assert panels["password"] == ""

    signed_out = ui_app._logout(state)
    assert signed_out[0] is None
    assert signed_out[1]["visible"] is True
    assert all(item["visible"] is False for item in signed_out[2:5])
    cleared = _panels(signed_out, ui_app.PANEL_RESET_KEYS)
    assert cleared["chatbot"] == []
    assert cleared["citations"] == []
    assert cleared["citation_detail"] == ui_app.CITATION_HINT
    assert cleared["password"] == ""


def test_failed_login_clears_panels_and_reports_credentials(
    api_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COURSE_FINDER_API_URL", api_url)
    from ui import app as ui_app

    state, *rest = ui_app._login("student-001", "wrong-password")
    assert state is None
    assert rest[0]["visible"] is True
    assert "Incorrect username or password" in rest[4]
    assert _panels((state, *rest), ui_app.PANEL_RESET_KEYS)["chatbot"] == []

    blank = ui_app._login("", "")
    assert blank[0] is None
    assert "Enter a username and password" in blank[5]
