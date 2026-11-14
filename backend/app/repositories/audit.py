"""Redacted local audit-event persistence for API access decisions."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from uuid import uuid4


class AuditRepository:
    """Append-only local audit log; never stores request bodies or source excerpts."""

    def __init__(self, database: Path):
        self.database = database.resolve()
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    actor_user_id TEXT,
                    actor_role TEXT,
                    action TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def record(
        self,
        *,
        actor_user_id: str | None,
        actor_role: str | None,
        action: str,
        resource_type: str,
        outcome: str,
        metadata: dict[str, str],
    ) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?)",
                (
                    f"audit-{uuid4()}",
                    actor_user_id,
                    actor_role,
                    action,
                    resource_type,
                    outcome,
                    datetime.now(UTC).isoformat(),
                    json.dumps(metadata, sort_keys=True),
                ),
            )

    def events(self) -> tuple[dict[str, object], ...]:
        """Expose records to tests/operators; never includes request payloads."""

        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM audit_events ORDER BY created_at,event_id"
            ).fetchall()
        return tuple(
            {
                "event_id": row["event_id"],
                "actor_user_id": row["actor_user_id"],
                "actor_role": row["actor_role"],
                "action": row["action"],
                "resource_type": row["resource_type"],
                "outcome": row["outcome"],
                "created_at": row["created_at"],
                "metadata": json.loads(row["metadata_json"]),
            }
            for row in rows
        )
