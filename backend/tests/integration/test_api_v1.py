from __future__ import annotations

import shutil
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings
from app.ingestion.readings import ingest_reading, load_reviews
from app.main import create_app


@pytest.fixture
def api_client(data_root: Path, tmp_path: Path) -> TestClient:
    isolated = tmp_path / "data"
    shutil.copytree(data_root / "samples", isolated / "samples")
    shutil.copytree(data_root / "manifests", isolated / "manifests")
    settings = Settings(
        app_env="test",
        data_root=isolated,
        local_dev_password=SecretStr("test-password"),
        session_secret=SecretStr("test-session-secret"),
        csrf_secret=SecretStr("test-csrf-secret"),
    )
    return TestClient(create_app(settings))


def login(client: TestClient, username: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "test-password"},
    )
    assert response.status_code == 200
    return response.json()["csrf_token"]


def test_openapi_has_single_version_prefix(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/students/me" in paths
    assert not any(path.startswith("/api/v1/api/v1") for path in paths)


def test_student_profile_progress_and_courses(api_client: TestClient) -> None:
    login(api_client, "student-001")

    me = api_client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["student_id"] == "student-001"

    profile = api_client.get("/api/v1/students/me")
    assert profile.status_code == 200
    assert {item["course_code"] for item in profile.json()["current_courses"]} == {
        "PHYS 350",
        "HIST 210",
        "ENGL 120",
    }

    progress = api_client.get("/api/v1/students/me/progress")
    assert progress.status_code == 200
    history = next(
        group for group in progress.json()["requirement_groups"] if group["group_id"] == "history"
    )
    assert history["state"] == "satisfied"

    courses = api_client.get("/api/v1/courses", params={"season": "Spring"})
    assert courses.status_code == 200
    assert courses.json()["total"] == 10

    course = api_client.get("/api/v1/courses/PHYS%20340")
    assert course.status_code == 200
    assert course.json()["prerequisite_course_ids"] == ["PHYS 230"]
    audit_events = cast(FastAPI, api_client.app).state.services.audit.events()
    profile_access = next(
        event
        for event in audit_events
        if event["action"] == "GET /students/me"
    )
    assert profile_access["actor_user_id"] == "user-student-001"
    assert profile_access["outcome"] == "allowed"
    assert "content" not in profile_access["metadata"]


@pytest.mark.acceptance
def test_planner_and_multi_turn_cap(api_client: TestClient) -> None:
    csrf = login(api_client, "student-001")

    plan_response = api_client.get(
        "/api/v1/academic-plan",
        params={"term": "Spring 2027", "unit_cap": 12},
    )
    assert plan_response.status_code == 200
    assert plan_response.json()["plan"]["total_units"] == 12

    thread = api_client.post(
        "/api/v1/chat/sessions",
        json={},
        headers={"X-CSRF-Token": csrf},
    )
    assert thread.status_code == 201
    thread_id = thread.json()["thread_id"]

    first = api_client.post(
        f"/api/v1/chat/sessions/{thread_id}/messages",
        json={
            "content": (
                "What should I take in Spring 2027 to progress my degree? Keep it to 12 units."
            )
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert first.status_code == 201
    assert first.json()["response"]["planning"]["total_units"] == 12

    second = api_client.post(
        f"/api/v1/chat/sessions/{thread_id}/messages",
        json={"content": "I have an internship, so cap me at 8 units."},
        headers={"X-CSRF-Token": csrf},
    )
    assert second.status_code == 201
    assert second.json()["response"]["planning"]["total_units"] == 8


def test_csrf_and_thread_ownership_are_enforced(api_client: TestClient) -> None:
    csrf = login(api_client, "student-001")
    missing_csrf = api_client.post("/api/v1/chat/sessions", json={})
    assert missing_csrf.status_code == 403
    created = api_client.post(
        "/api/v1/chat/sessions",
        json={},
        headers={"X-CSRF-Token": csrf},
    )
    thread_id = created.json()["thread_id"]

    other = TestClient(api_client.app)
    login(other, "student-002")
    assert other.get(f"/api/v1/chat/sessions/{thread_id}").status_code == 404


@pytest.mark.acceptance
def test_unsupported_fact_is_not_invented_over_http(api_client: TestClient) -> None:
    csrf = login(api_client, "student-001")
    created = api_client.post(
        "/api/v1/chat/sessions",
        json={},
        headers={"X-CSRF-Token": csrf},
    )
    thread_id = created.json()["thread_id"]
    response = api_client.post(
        f"/api/v1/chat/sessions/{thread_id}/messages",
        json={"content": "Are there seats available for Spring 2027 courses?"},
        headers={"X-CSRF-Token": csrf},
    )
    answer = response.json()["response"]
    assert answer["status"] == "unsupported"
    assert "does not support this request" in answer["text"]
    assert answer["citations"] == []


@pytest.mark.acceptance
def test_adviser_assignment_and_admin_role_are_enforced(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    login(api_client, "adviser-001")
    assigned = api_client.get("/api/v1/advisers/students/student-001")
    assert assigned.status_code == 200
    assert assigned.json()["student"]["student_id"] == "student-001"
    assert api_client.get("/api/v1/advisers/students/student-002").status_code == 404
    assigned_plan = api_client.get(
        "/api/v1/academic-plan",
        params={"term": "Spring 2027", "student_id": "student-001"},
    )
    assert assigned_plan.status_code == 200
    denied_student_plan = api_client.get(
        "/api/v1/academic-plan",
        params={"term": "Spring 2027", "student_id": "student-002"},
    )
    assert denied_student_plan.status_code == 404
    assert api_client.get("/api/v1/admin/ingestions/missing").status_code == 403

    admin = TestClient(api_client.app)
    csrf = login(admin, "admin")
    assert admin.get("/api/v1/admin/ingestions/missing").status_code == 404
    assert admin.post("/api/v1/admin/ingestions", json={}).status_code == 403
    services = cast(FastAPI, api_client.app).state.services
    monkeypatch.setattr(services.ingestion_jobs, "run", lambda job_id: None)
    started = admin.post(
        "/api/v1/admin/ingestions",
        json={},
        headers={"X-CSRF-Token": csrf},
    )
    assert started.status_code == 202
    job_id = started.json()["job_id"]
    assert admin.get(f"/api/v1/admin/ingestions/{job_id}").json()["status"] == "queued"


def test_local_auth_requires_non_placeholder_password(data_root: Path) -> None:
    settings = Settings(
        app_env="test",
        data_root=data_root,
        local_dev_password=SecretStr("replace-me-local-only"),
    )
    client = TestClient(create_app(settings))
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "student-001", "password": "replace-me-local-only"},
    )
    assert response.status_code == 503


def test_invalid_password_is_rejected(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/v1/auth/login",
        json={"username": "student-001", "password": "wrong"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password."


def test_request_body_limit_and_audit_metadata_redaction(api_client: TestClient) -> None:
    oversized = api_client.post(
        "/api/v1/chat/sessions",
        content=b"x" * (1_048_576 + 1),
        headers={"Content-Type": "application/json"},
    )
    assert oversized.status_code == 413

    csrf = login(api_client, "student-001")
    response = api_client.post(
        "/api/v1/chat/sessions",
        json={},
        headers={"X-CSRF-Token": csrf, "Authorization": "Bearer sensitive-test-token"},
    )
    assert response.status_code == 201
    events = cast(FastAPI, api_client.app).state.services.audit.events()
    assert "sensitive-test-token" not in repr(events)


def test_logout_revokes_session_and_login_is_rate_limited(api_client: TestClient) -> None:
    csrf = login(api_client, "student-001")
    logout = api_client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": csrf},
    )
    assert logout.status_code == 200
    audit = cast(FastAPI, api_client.app).state.services.audit
    event = audit.events()[-1]
    assert event["action"] == "POST /auth/logout"
    assert event["actor_user_id"] == "user-student-001"
    assert event["actor_role"] == "student"
    assert api_client.get("/api/v1/auth/me").status_code == 401

    client = TestClient(api_client.app)
    for _ in range(5):
        failed = client.post(
            "/api/v1/auth/login",
            json={"username": "student-001", "password": "wrong"},
        )
        assert failed.status_code == 401
    limited = client.post(
        "/api/v1/auth/login",
        json={"username": "student-001", "password": "test-password"},
    )
    assert limited.status_code == 429


def test_student_materials_and_adviser_assignment_list(api_client: TestClient) -> None:
    login(api_client, "student-001")
    materials = api_client.get("/api/v1/students/me/materials")
    assert materials.status_code == 200
    payload = materials.json()
    assert payload["student_id"] == "student-001"
    assert {course["course_code"] for course in payload["courses"]} == {
        "PHYS 350",
        "HIST 210",
        "ENGL 120",
    }
    bohr = next(
        course for course in payload["courses"] if course["course_code"] == "PHYS 350"
    )
    reading = bohr["readings"][0]
    assert reading["document_id"] == "phys350-bohr-model"
    assert reading["ingested"] is False
    assert reading["page_count"] == 12
    assert reading["approved_assets"] == 0

    assert api_client.get("/api/v1/advisers/students").status_code == 403

    adviser = TestClient(api_client.app)
    login(adviser, "adviser-001")
    assigned = adviser.get("/api/v1/advisers/students")
    assert assigned.status_code == 200
    assert [item["student_id"] for item in assigned.json()] == ["student-001"]

    other = TestClient(api_client.app)
    login(other, "adviser-002")
    assert [item["student_id"] for item in other.get("/api/v1/advisers/students").json()] == [
        "student-002"
    ]


@pytest.mark.acceptance
@pytest.mark.corpus
def test_bohr_conversation_and_owner_scoped_citations(api_client: TestClient) -> None:
    services = cast(FastAPI, api_client.app).state.services
    dataset = services.dataset()
    document = dataset.catalog.document("phys350-bohr-model")
    assert document is not None
    reviews = load_reviews(services.settings.manifests_dir / "reading_qa.json")
    ingest_reading(
        document,
        services.settings.course_materials_dir,
        services.readings,
        reviews.documents[document.document_id],
    )

    csrf = login(api_client, "student-001")
    created = api_client.post(
        "/api/v1/chat/sessions",
        json={},
        headers={"X-CSRF-Token": csrf},
    )
    thread_id = created.json()["thread_id"]

    prose = api_client.post(
        f"/api/v1/chat/sessions/{thread_id}/messages",
        json={"content": "How does the Bohr model explain the hydrogen spectrum?"},
        headers={"X-CSRF-Token": csrf},
    )
    assert prose.status_code == 201
    citations = prose.json()["response"]["citations"]
    assert citations
    assert citations[0]["document_title"] == "Bohr model"
    citation_response = api_client.get(
        f"/api/v1/chat/sessions/{thread_id}/citations/{citations[0]['chunk_id']}"
    )
    assert citation_response.status_code == 200
    assert citation_response.json()["page_number"] == citations[0]["pdf_page_number"]

    equation = api_client.post(
        f"/api/v1/chat/sessions/{thread_id}/messages",
        json={
            "content": (
                "According to the equation on PDF page 7, can you explain it in "
                "simpler terms?"
            )
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert equation.status_code == 201
    assert equation.json()["response"]["status"] == "insufficient_evidence"
    assert not equation.json()["response"]["citations"]

    ambiguous = api_client.post(
        f"/api/v1/chat/sessions/{thread_id}/messages",
        json={
            "content": (
                "According to the diagram in that reading, how many electrons "
                "can the second energy level hold?"
            )
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert ambiguous.json()["response"]["status"] == "clarification_required"

    exact = api_client.post(
        f"/api/v1/chat/sessions/{thread_id}/messages",
        json={
            "content": (
                "I mean Figure 2. How many electrons can the second energy level "
                "hold according to its label?"
            )
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert exact.status_code == 201
    exact_response = exact.json()["response"]
    assert "up to 8 electrons" in exact_response["text"]
    visual_citation = exact_response["citations"][0]
    assert visual_citation["pdf_page_number"] == 4

    asset = api_client.get(
        f"/api/v1/chat/sessions/{thread_id}/assets/{visual_citation['asset_id']}"
    )
    assert asset.status_code == 200
    assert asset.headers["content-type"] == "image/png"
    assert asset.headers["cache-control"] == "private, no-store"

    page_render = api_client.get(
        f"/api/v1/chat/sessions/{thread_id}/documents/phys350-bohr-model/pages/4"
    )
    assert page_render.status_code == 200
    assert page_render.headers["content-type"] == "image/png"
    assert page_render.headers["cache-control"] == "private, no-store"

    # In scope, but not cited in this thread: no browsing beyond conversation evidence.
    assert (
        api_client.get(
            f"/api/v1/chat/sessions/{thread_id}/documents/hist210-niels-bohr/pages/1"
        ).status_code
        == 404
    )
    # Outside the student's current-course scope.
    assert (
        api_client.get(
            f"/api/v1/chat/sessions/{thread_id}/documents/phys230-critical-mass/pages/1"
        ).status_code
        == 404
    )

    materials = api_client.get("/api/v1/students/me/materials").json()
    bohr = next(
        course for course in materials["courses"] if course["course_code"] == "PHYS 350"
    )
    assert bohr["readings"][0]["ingested"] is True
    assert bohr["readings"][0]["approved_assets"] == 2

    other = TestClient(api_client.app)
    login(other, "student-002")
    assert (
        other.get(
            f"/api/v1/chat/sessions/{thread_id}/citations/{citations[0]['chunk_id']}"
        ).status_code
        == 404
    )
    assert (
        other.get(
            f"/api/v1/chat/sessions/{thread_id}/assets/{visual_citation['asset_id']}"
        ).status_code
        == 404
    )
    assert (
        other.get(
            f"/api/v1/chat/sessions/{thread_id}/documents/phys350-bohr-model/pages/4"
        ).status_code
        == 404
    )


def test_unknown_username_verifies_dummy_hash(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = cast(FastAPI, api_client.app).state.services.auth
    hashes: list[str] = []

    def verify(password: str, credential_hash: str) -> bool:
        hashes.append(credential_hash)
        return True

    monkeypatch.setattr(auth._password_hash, "verify", verify)
    response = api_client.post(
        "/api/v1/auth/login",
        json={"username": "unknown", "password": "wrong"},
    )
    assert response.status_code == 401
    assert hashes == [auth._dummy_hash]


@pytest.mark.parametrize("student_id", ["student-001", "student-002"])
def test_conversation_uses_atomic_snapshot(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch, student_id: str
) -> None:
    csrf = login(api_client, "student-001")
    created = api_client.post(
        "/api/v1/chat/sessions", json={}, headers={"X-CSRF-Token": csrf}
    )
    thread_id = created.json()["thread_id"]
    repository = cast(FastAPI, api_client.app).state.services.conversations
    snapshot = repository.get_with_messages(thread_id, "user-student-001")
    snapshot = (snapshot[0].model_copy(update={"authorized_student_id": student_id}), snapshot[1])
    calls = []

    def read_snapshot(thread_id: str, owner_id: str):
        calls.append((thread_id, owner_id))
        return snapshot

    def separate_read(*args):
        pytest.fail("conversation must be read atomically")

    monkeypatch.setattr(repository, "get_with_messages", read_snapshot)
    monkeypatch.setattr(repository, "get", separate_read)
    monkeypatch.setattr(repository, "messages", separate_read)
    response = api_client.get(f"/api/v1/chat/sessions/{thread_id}")
    assert response.status_code == (200 if student_id == "student-001" else 404)
    if student_id == "student-001":
        assert response.json()["revision"] == snapshot[0].revision
    assert calls == [(thread_id, "user-student-001")]


def test_failed_request_is_audited_off_loop_and_preserves_exception(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    application = cast(FastAPI, api_client.app)
    audit = application.state.services.audit
    original_record = audit.record
    failure = RuntimeError("endpoint failed")

    def record(**kwargs):
        with pytest.raises(RuntimeError, match="no running event loop"):
            asyncio.get_running_loop()
        original_record(**kwargs)

    monkeypatch.setattr(audit, "record", record)

    @application.get("/api/v1/test-failure")
    async def fail():
        raise failure

    login(api_client, "student-001")
    with pytest.raises(RuntimeError) as caught:
        api_client.get("/api/v1/test-failure")
    assert caught.value is failure
    event = audit.events()[-1]
    assert event["action"] == "GET /api/v1/test-failure"
    assert event["actor_user_id"] == "user-student-001"
    assert event["actor_role"] == "student"
    assert event["outcome"] == "denied"
    assert event["metadata"] == {"http_status": "500"}


def test_cited_page_rejects_replaced_ingestion(api_client: TestClient, synthetic) -> None:
    services = cast(FastAPI, api_client.app).state.services
    samples, synthetic_document, review, _ = synthetic
    document = synthetic_document.model_copy(update={
        "document_id": "phys350-bohr-model", "course_id": "PHYS 350", "title": "Bohr model"
    })
    first = ingest_reading(document, samples, services.readings, review)
    csrf = login(api_client, "student-001")
    headers = {"X-CSRF-Token": csrf}
    thread_id = api_client.post(
        "/api/v1/chat/sessions", json={}, headers=headers
    ).json()["thread_id"]
    answer = api_client.post(
        f"/api/v1/chat/sessions/{thread_id}/messages",
        json={"content": "How does the Bohr model explain the hydrogen spectrum?"},
        headers=headers,
    )
    assert answer.status_code == 201
    citation = answer.json()["response"]["citations"][0]
    assert citation["ingestion_version"] == first.ingestion_version
    path = (
        f"/api/v1/chat/sessions/{thread_id}/documents/{document.document_id}"
        f"/pages/{citation['pdf_page_number']}"
    )
    assert api_client.get(path).status_code == 200
    second = ingest_reading(
        document.model_copy(update={"title": document.title + " revised"}),
        samples, services.readings, review,
    )
    assert second.ingestion_version != first.ingestion_version
    active, _ = services.readings.active_reading(
        document.document_id, frozenset({document.document_id})
    )
    assert active.ingestion_version == second.ingestion_version
    assert api_client.get(path).status_code == 404
    versioned_path = path + "?ingestion_version=" + first.ingestion_version
    assert api_client.get(versioned_path).status_code == 404
    new_answer = api_client.post(
        f"/api/v1/chat/sessions/{thread_id}/messages",
        json={"content": "How does the Bohr model explain the hydrogen spectrum?"},
        headers=headers,
    )
    assert new_answer.status_code == 201
    new_citation = new_answer.json()["response"]["citations"][0]
    assert new_citation["ingestion_version"] == second.ingestion_version
    assert api_client.get(path).status_code == 200
    assert api_client.get(versioned_path).status_code == 404
