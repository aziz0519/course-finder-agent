from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings
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
        group
        for group in progress.json()["requirement_groups"]
        if group["group_id"] == "history"
    )
    assert history["state"] == "satisfied"

    courses = api_client.get("/api/v1/courses", params={"season": "Spring"})
    assert courses.status_code == 200
    assert courses.json()["total"] == 10

    course = api_client.get("/api/v1/courses/PHYS%20340")
    assert course.status_code == 200
    assert course.json()["prerequisite_course_ids"] == ["PHYS 230"]


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
                "What should I take in Spring 2027 to progress my degree? "
                "Keep it to 12 units."
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


def test_adviser_assignment_and_admin_role_are_enforced(api_client: TestClient) -> None:
    login(api_client, "adviser-001")
    assigned = api_client.get("/api/v1/advisers/students/student-001")
    assert assigned.status_code == 200
    assert assigned.json()["student"]["student_id"] == "student-001"
    assert api_client.get("/api/v1/advisers/students/student-002").status_code == 404
    assert api_client.get("/api/v1/admin/ingestions/missing").status_code == 403

    admin = TestClient(api_client.app)
    login(admin, "admin")
    assert admin.get("/api/v1/admin/ingestions/missing").status_code == 404


def test_invalid_password_is_rejected(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/v1/auth/login",
        json={"username": "student-001", "password": "wrong"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password."
