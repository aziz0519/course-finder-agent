import pytest

from app.agents.models import AgentResponse, ConversationState, TraceEvent
from app.repositories.conversations import ConversationRepository


def test_thread_owner_scope_and_atomic_turn(tmp_path) -> None:
    repository = ConversationRepository(tmp_path / "conversations.sqlite3")
    thread = repository.create("user-001", "student-001")
    response = AgentResponse(status="ok", intent="planner", text="A response")
    state = ConversationState(last_intent="planner", planning_unit_cap=8)

    updated = repository.append_turn(thread, "Cap me at 8 units", response, state)

    assert updated.state.planning_unit_cap == 8
    messages = repository.messages(thread.thread_id, "user-001")
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[1].response == response
    assert repository.get(thread.thread_id, "user-001").state == state
    with pytest.raises(PermissionError):
        repository.get(thread.thread_id, "another-user")


def test_trace_metadata_is_redacted_and_owner_scoped(tmp_path) -> None:
    repository = ConversationRepository(tmp_path / "conversations.sqlite3")
    thread = repository.create("user-001", "student-001")
    trace = TraceEvent(
        trace_id="trace-1",
        agent_name="planner",
        status="ok",
        metadata={"intent": "planner"},
    )
    response = AgentResponse(
        status="ok", intent="planner", text="A response", trace_ids=(trace.trace_id,)
    )
    repository.append_turn(
        thread,
        "Plan my courses",
        response,
        ConversationState(last_intent="planner"),
        traces=(trace,),
    )
    assert repository.agent_runs(thread.thread_id, "user-001")[0].trace == trace
    with pytest.raises(PermissionError):
        repository.agent_runs(thread.thread_id, "another-user")


def test_stale_checkpoint_is_rejected(tmp_path) -> None:
    repository = ConversationRepository(tmp_path / "conversations.sqlite3")
    stale = repository.create("user-001", "student-001")
    repository.append_turn(
        stale,
        "First",
        AgentResponse(status="ok", intent="planner", text="First"),
        ConversationState(last_intent="planner"),
    )
    with pytest.raises(RuntimeError, match="stale"):
        repository.append_turn(
            stale,
            "Conflicting",
            AgentResponse(status="ok", intent="tutor", text="Conflicting"),
            ConversationState(last_intent="tutor"),
        )
    assert len(repository.messages(stale.thread_id, "user-001")) == 2


def test_failed_turn_rolls_back_messages_and_checkpoint(tmp_path) -> None:
    repository = ConversationRepository(tmp_path / "conversations.sqlite3")
    thread = repository.create("user-001", "student-001")
    with repository.connect() as db:
        db.execute(
            "CREATE TRIGGER fail_assistant BEFORE INSERT ON conversation_messages "
            "WHEN NEW.role='assistant' BEGIN SELECT RAISE(ABORT,'simulated failure'); END"
        )
    with pytest.raises(Exception, match="simulated failure"):
        repository.append_turn(
            thread,
            "Question",
            AgentResponse(status="ok", intent="tutor", text="Answer"),
            ConversationState(last_intent="tutor"),
        )
    assert repository.messages(thread.thread_id, "user-001") == ()
    stored = repository.get(thread.thread_id, "user-001")
    assert stored.state == ConversationState()
    assert stored.revision == 0


def test_checkpoint_and_messages_share_read_snapshot(tmp_path, monkeypatch):
    from contextlib import contextmanager

    repository = ConversationRepository(tmp_path / "conversations.sqlite3")
    thread = repository.create("owner", "student-001")
    with repository.connect() as db:
        db.execute("PRAGMA journal_mode=WAL")
    original_connect = repository.connect
    interleaved = False

    @contextmanager
    def interleave():
        nonlocal interleaved
        with original_connect() as db:

            def on_query(query):
                nonlocal interleaved
                if "SELECT * FROM conversation_messages" in query and not interleaved:
                    interleaved = True
                    repository.append_turn(
                        thread,
                        "Question",
                        AgentResponse(status="ok", intent="planner", text="Answer"),
                        ConversationState(last_intent="planner"),
                    )

            db.set_trace_callback(on_query)
            yield db

    monkeypatch.setattr(repository, "connect", interleave)
    checkpoint, messages = repository.get_with_messages(thread.thread_id, "owner")
    assert interleaved
    assert checkpoint.revision == 0
    assert messages == ()
    checkpoint, messages = repository.get_with_messages(thread.thread_id, "owner")
    assert checkpoint.revision == 1
    assert len(messages) == 2
    with pytest.raises(PermissionError):
        repository.get_with_messages(thread.thread_id, "other")
