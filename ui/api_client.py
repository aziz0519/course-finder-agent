"""Small HTTP client for the local M4 API.

The UI never imports backend services: it talks to the API exactly as a browser
would, so every request re-enters the authenticated, authorized boundary. Session
state is kept as plain strings so it can live in a per-browser Gradio state value.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import httpx

SESSION_COOKIE = "course_finder_session"
DEFAULT_API_URL = "http://127.0.0.1:8000"
DEFAULT_TERM = "Spring 2027"


class ApiError(Exception):
    """A non-2xx API response, carrying only the server's public detail."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"{status_code}: {detail}")


@dataclass(frozen=True)
class SessionState:
    user_id: str
    role: str
    student_id: str | None
    adviser_id: str | None
    csrf_token: str
    cookie: str


def _detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.reason_phrase or "Request failed."
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list) and detail:
        first = detail[0]
        if isinstance(first, dict) and isinstance(first.get("msg"), str):
            return first["msg"]
    return response.reason_phrase or "Request failed."


class ApiClient:
    """One short-lived client per UI event; the cookie and CSRF token are data."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = (
            base_url or os.environ.get("COURSE_FINDER_API_URL") or DEFAULT_API_URL
        ).rstrip("/")
        self._timeout = timeout
        self.transport = transport
        self._cookie: str | None = None
        self._csrf: str | None = None

    @classmethod
    def from_session(cls, state: SessionState, **kwargs: Any) -> ApiClient:
        client = cls(**kwargs)
        client._cookie = state.cookie
        client._csrf = state.csrf_token
        return client

    @contextmanager
    def _connection(self) -> Iterator[httpx.Client]:
        with httpx.Client(
            base_url=self.base_url,
            timeout=self._timeout,
            transport=self.transport,
        ) as client:
            if self._cookie:
                client.cookies.set(SESSION_COOKIE, self._cookie)
            if self._csrf:
                client.headers["X-CSRF-Token"] = self._csrf
            yield client

    def _json(self, method: str, path: str, **kwargs: Any) -> Any:
        with self._connection() as client:
            response = client.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise ApiError(response.status_code, _detail(response))
        if not response.content:
            return {}
        return response.json()

    def _bytes(self, path: str) -> bytes:
        with self._connection() as client:
            response = client.get(path)
        if response.status_code >= 400:
            raise ApiError(response.status_code, _detail(response))
        return response.content

    # --- authentication ---------------------------------------------------------

    def login(self, username: str, password: str) -> SessionState:
        with httpx.Client(
            base_url=self.base_url,
            timeout=self._timeout,
            transport=self.transport,
        ) as client:
            response = client.post(
                "/api/v1/auth/login",
                json={"username": username, "password": password},
            )
            if response.status_code >= 400:
                raise ApiError(response.status_code, _detail(response))
            body = response.json()
            cookie = client.cookies.get(SESSION_COOKIE)
        if not cookie:
            raise ApiError(500, "The API did not issue a session cookie.")
        return SessionState(
            user_id=body["user_id"],
            role=body["role"],
            student_id=body.get("student_id"),
            adviser_id=body.get("adviser_id"),
            csrf_token=body["csrf_token"],
            cookie=cookie,
        )

    def logout(self) -> None:
        self._json("POST", "/api/v1/auth/logout")

    # --- student ----------------------------------------------------------------

    def profile(self) -> dict[str, Any]:
        return self._json("GET", "/api/v1/students/me")

    def progress(self) -> dict[str, Any]:
        return self._json("GET", "/api/v1/students/me/progress")

    def materials(self) -> dict[str, Any]:
        return self._json("GET", "/api/v1/students/me/materials")

    def plan(
        self,
        *,
        term: str = DEFAULT_TERM,
        unit_cap: int | None = None,
        student_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"term": term}
        if unit_cap is not None:
            params["unit_cap"] = unit_cap
        if student_id:
            params["student_id"] = student_id
        return self._json("GET", "/api/v1/academic-plan", params=params)

    # --- conversations ----------------------------------------------------------

    def create_thread(self) -> dict[str, Any]:
        return self._json("POST", "/api/v1/chat/sessions", json={})

    def list_threads(self) -> list[dict[str, Any]]:
        return self._json("GET", "/api/v1/chat/sessions")

    def thread(self, thread_id: str) -> dict[str, Any]:
        return self._json("GET", f"/api/v1/chat/sessions/{thread_id}")

    def send(self, thread_id: str, content: str) -> dict[str, Any]:
        return self._json(
            "POST",
            f"/api/v1/chat/sessions/{thread_id}/messages",
            json={"content": content},
        )

    def citation(self, thread_id: str, chunk_id: str) -> dict[str, Any]:
        return self._json(
            "GET",
            f"/api/v1/chat/sessions/{thread_id}/citations/{chunk_id}",
        )

    def asset_bytes(self, thread_id: str, asset_id: str) -> bytes:
        return self._bytes(
            f"/api/v1/chat/sessions/{thread_id}/assets/{asset_id}"
        )

    def page_bytes(self, thread_id: str, document_id: str, page_number: int) -> bytes:
        return self._bytes(
            f"/api/v1/chat/sessions/{thread_id}/documents/{document_id}"
            f"/pages/{page_number}"
        )

    # --- adviser ----------------------------------------------------------------

    def assigned_students(self) -> list[dict[str, Any]]:
        return self._json("GET", "/api/v1/advisers/students")

    def assigned_student(self, student_id: str) -> dict[str, Any]:
        return self._json("GET", f"/api/v1/advisers/students/{student_id}")

    # --- admin ------------------------------------------------------------------

    def start_ingestion(self) -> dict[str, Any]:
        return self._json("POST", "/api/v1/admin/ingestions", json={})

    def ingestion(self, job_id: str) -> dict[str, Any]:
        return self._json("GET", f"/api/v1/admin/ingestions/{job_id}")
