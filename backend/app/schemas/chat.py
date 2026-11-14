"""Conversation API contracts."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.agents.models import AgentResponse, ConversationState


class ConversationCreate(BaseModel):
    pass


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class StoredMessageResponse(BaseModel):
    message_id: str
    role: str
    content: str
    created_at: datetime
    sequence: int
    response: AgentResponse | None = None


class ConversationSummaryResponse(BaseModel):
    thread_id: str
    created_at: datetime
    updated_at: datetime
    revision: int
    state: ConversationState


class ConversationResponse(ConversationSummaryResponse):
    messages: tuple[StoredMessageResponse, ...]


class MessageResponse(BaseModel):
    thread_id: str
    response: AgentResponse
