from app.agents.models import ConversationState
from app.agents.supervisor import route_intent


def test_routes_planning_and_tutoring() -> None:
    state = ConversationState()
    assert route_intent("What should I take in Spring 2027?", state) == "planner"
    assert route_intent("Explain the Bohr model", state) == "tutor"
    assert route_intent("What is the weather?", state) == "unsupported"


def test_routes_contextual_follow_ups() -> None:
    planner = ConversationState(last_intent="planner", planning_unit_cap=12)
    assert route_intent("Cap me at 8 units", planner) == "planner"
    tutor = ConversationState(
        last_intent="tutor",
        active_course_id="PHYS 350",
        active_document_id="phys350-bohr-model",
    )
    assert route_intent("What does that source mean?", tutor) == "tutor"
