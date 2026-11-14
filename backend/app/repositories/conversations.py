"""Local M3 conversation persistence with owner and student-scope checks.

This is a development adapter, not the M4 authentication layer. Callers still have to
provide a verified actor and authorized student scope. The repository prevents a caller
from replaying another actor's thread and updates a turn plus checkpoint atomically.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import Field

from app.agents.models import AgentResponse, ConversationState
from app.domain.models import DomainModel


class ConversationThread(DomainModel):
    thread_id: str
    owner_user_id: str
    authorized_student_id: str
    state: ConversationState
    created_at: datetime
    updated_at: datetime


class StoredMessage(DomainModel):
    message_id: str
    thread_id: str
    role: str
    content: str
    response: AgentResponse | None = None
    created_at: datetime
    sequence: int = Field(ge=1)


class ConversationRepository:
    def __init__(self, database: Path):
        self.database = database.resolve()
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    thread_id TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL,
                    authorized_student_id TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    message_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL REFERENCES conversations(thread_id),
                    sequence INTEGER NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                    content TEXT NOT NULL,
                    response_json TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(thread_id, sequence)
                );
                """
            )

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, owner_user_id: str, authorized_student_id: str) -> ConversationThread:
        if not owner_user_id or not authorized_student_id:
            raise ValueError("owner and authorized student are required")
        now = datetime.now(UTC)
        thread = ConversationThread(
            thread_id=f"thread-{uuid4()}",
            owner_user_id=owner_user_id,
            authorized_student_id=authorized_student_id,
            state=ConversationState(),
            created_at=now,
            updated_at=now,
        )
        with self.connect() as db:
            db.execute(
                "INSERT INTO conversations VALUES (?,?,?,?,?,?)",
                (
                    thread.thread_id,
                    thread.owner_user_id,
                    thread.authorized_student_id,
                    thread.state.model_dump_json(),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
        return thread

    def get(self, thread_id: str, owner_user_id: str) -> ConversationThread:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM conversations WHERE thread_id=? AND owner_user_id=?",
                (thread_id, owner_user_id),
            ).fetchone()
        if row is None:
            # Do not disclose whether another owner has this ID.
            raise PermissionError("conversation unavailable")
        return ConversationThread(
            thread_id=row["thread_id"],
            owner_user_id=row["owner_user_id"],
            authorized_student_id=row["authorized_student_id"],
            state=ConversationState.model_validate_json(row["state_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def append_turn(
        self,
        thread: ConversationThread,
        user_content: str,
        response: AgentResponse,
        state: ConversationState,
    ) -> ConversationThread:
        now = datetime.now(UTC)
        with self.connect() as db:
            current = db.execute(
                "SELECT owner_user_id,authorized_student_id FROM conversations WHERE thread_id=?",
                (thread.thread_id,),
            ).fetchone()
            if (
                current is None
                or current["owner_user_id"] != thread.owner_user_id
                or current["authorized_student_id"] != thread.authorized_student_id
            ):
                raise PermissionError("conversation unavailable")
            sequence = db.execute(
                "SELECT COALESCE(MAX(sequence),0) FROM conversation_messages WHERE thread_id=?",
                (thread.thread_id,),
            ).fetchone()[0]
            db.executemany(
                "INSERT INTO conversation_messages VALUES (?,?,?,?,?,?,?)",
                (
                    (
                        f"message-{uuid4()}",
                        thread.thread_id,
                        sequence + 1,
                        "user",
                        user_content,
                        None,
                        now.isoformat(),
                    ),
                    (
                        f"message-{uuid4()}",
                        thread.thread_id,
                        sequence + 2,
                        "assistant",
                        response.text,
                        response.model_dump_json(),
                        now.isoformat(),
                    ),
                ),
            )
            db.execute(
                "UPDATE conversations SET state_json=?,updated_at=? WHERE thread_id=?",
                (state.model_dump_json(), now.isoformat(), thread.thread_id),
            )
        return thread.model_copy(update={"state": state, "updated_at": now})

    def messages(self, thread_id: str, owner_user_id: str) -> tuple[StoredMessage, ...]:
        self.get(thread_id, owner_user_id)
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM conversation_messages WHERE thread_id=? ORDER BY sequence",
                (thread_id,),
            ).fetchall()
        return tuple(
            StoredMessage(
                message_id=row["message_id"],
                thread_id=row["thread_id"],
                role=row["role"],
                content=row["content"],
                response=(
                    AgentResponse.model_validate_json(row["response_json"])
                    if row["response_json"]
                    else None
                ),
                created_at=datetime.fromisoformat(row["created_at"]),
                sequence=row["sequence"],
            )
            for row in rows
        )
