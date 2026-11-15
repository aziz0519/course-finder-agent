from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.repositories.audit import AuditRepository


def test_audit_connections_close_and_transactions_remain_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connections: list[sqlite3.Connection] = []
    connect = AuditRepository._connect

    def tracked_connect(self: AuditRepository) -> sqlite3.Connection:
        connection = connect(self)
        connections.append(connection)
        return connection

    monkeypatch.setattr(AuditRepository, "_connect", tracked_connect)
    repository = AuditRepository(tmp_path / "audit.sqlite")
    def record(action: str) -> None:
        repository.record(
            actor_user_id="user-test",
            actor_role="student",
            action=action,
            resource_type="test",
            outcome="allowed",
            metadata={},
        )

    record("GET /api/v1/test")
    assert len(repository.events()) == 1
    with pytest.raises(sqlite3.IntegrityError):
        record(None)  # type: ignore[arg-type]
    assert len(repository.events()) == 1
    assert len(connections) == 5
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")
