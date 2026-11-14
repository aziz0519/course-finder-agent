"""Secure, local-development authentication and session management."""

from __future__ import annotations

import hashlib
import secrets
import threading
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from pwdlib import PasswordHash
from pydantic import BaseModel, ConfigDict

from app.core.config import Settings

Role = Literal["student", "adviser", "admin"]


class Principal(BaseModel):
    """Verified application identity; request bodies never construct this object."""

    model_config = ConfigDict(frozen=True)

    user_id: str
    username: str
    role: Role
    student_id: str | None = None
    adviser_id: str | None = None


@dataclass(frozen=True)
class _Session:
    principal: Principal
    csrf_digest: str
    expires_at: datetime


class LoginRateLimitedError(Exception):
    """Raised after too many failed login attempts."""


class LocalAuthService:
    """Argon2id credentials plus opaque, revocable local sessions."""

    _USERS = (
        Principal(
            user_id="user-student-001",
            username="student-001",
            role="student",
            student_id="student-001",
        ),
        Principal(
            user_id="user-student-002",
            username="student-002",
            role="student",
            student_id="student-002",
        ),
        Principal(
            user_id="user-adviser-001",
            username="adviser-001",
            role="adviser",
            adviser_id="adviser-001",
        ),
        Principal(
            user_id="user-adviser-002",
            username="adviser-002",
            role="adviser",
            adviser_id="adviser-002",
        ),
        Principal(user_id="user-admin", username="admin", role="admin"),
    )

    def __init__(self, settings: Settings):
        self._password_hash = PasswordHash.recommended()
        password = settings.local_dev_password.get_secret_value()
        self._credential_hashes = {
            principal.username: self._password_hash.hash(password) for principal in self._USERS
        }
        self._principals = {principal.username: principal for principal in self._USERS}
        self._sessions: dict[str, _Session] = {}
        self._failures: defaultdict[str, deque[datetime]] = defaultdict(deque)
        self._ttl = timedelta(seconds=settings.session_ttl_seconds)
        self._lock = threading.RLock()

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def login(self, username: str, password: str, client_key: str) -> tuple[str, str, Principal]:
        """Verify credentials and return an opaque token, CSRF token, and principal."""

        now = datetime.now(UTC)
        with self._lock:
            failures = self._failures[client_key]
            while failures and now - failures[0] > timedelta(minutes=1):
                failures.popleft()
            if len(failures) >= 5:
                raise LoginRateLimitedError

            principal = self._principals.get(username)
            credential_hash = self._credential_hashes.get(username)
            if (
                principal is None
                or credential_hash is None
                or not self._password_hash.verify(password, credential_hash)
            ):
                failures.append(now)
                raise ValueError("invalid credentials")

            failures.clear()
            token = secrets.token_urlsafe(32)
            csrf = secrets.token_urlsafe(32)
            self._sessions[self._digest(token)] = _Session(
                principal=principal,
                csrf_digest=self._digest(csrf),
                expires_at=now + self._ttl,
            )
            return token, csrf, principal

    def authenticate(self, token: str | None) -> Principal | None:
        if not token:
            return None
        digest = self._digest(token)
        with self._lock:
            session = self._sessions.get(digest)
            if session is None:
                return None
            if session.expires_at <= datetime.now(UTC):
                self._sessions.pop(digest, None)
                return None
            return session.principal

    def verify_csrf(self, token: str | None, csrf: str | None) -> bool:
        if not token or not csrf:
            return False
        with self._lock:
            session = self._sessions.get(self._digest(token))
            return bool(
                session
                and session.expires_at > datetime.now(UTC)
                and secrets.compare_digest(session.csrf_digest, self._digest(csrf))
            )

    def logout(self, token: str | None) -> None:
        if token:
            with self._lock:
                self._sessions.pop(self._digest(token), None)
