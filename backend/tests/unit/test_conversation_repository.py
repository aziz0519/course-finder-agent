import pytest

from app.agents.models import AgentResponse, ConversationState
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
