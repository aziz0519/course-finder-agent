"""Bounded intent routing. The supervisor has no data-store or retrieval access."""

from __future__ import annotations

import re

from app.agents.models import ConversationState, Intent

PLANNING = re.compile(
    r"\b(spring 2027|academic plan|degree|course[s]? should|take in|unit[s]?"
    r"|prerequisite|eligible|internship|cap me)\b",
    re.IGNORECASE,
)
TUTOR = re.compile(
    r"\b(reading|explain|diagram|figure|chart|table|equation|formula|spectrum"
    r"|energy level|raven|bohr|critical mass|fissile|nuclear weapon)\b",
    re.IGNORECASE,
)


def route_intent(message: str, state: ConversationState) -> Intent:
    """Classify only enough to select a typed specialist.

    Planning cap follow-ups remain with the planner. Visual/source follow-ups remain
    with the tutor. Ambiguous unrelated text is not sent to arbitrary tools.
    """

    if PLANNING.search(message):
        return "planner"
    if TUTOR.search(message):
        return "tutor"
    if state.last_intent == "planner" and re.search(r"\b(cap|units?|course)\b", message, re.I):
        return "planner"
    if state.last_intent == "tutor" and state.active_document_id and re.search(
        r"\b(it|that|this|source|page)\b", message, re.I
    ):
        return "tutor"
    return "unsupported"
