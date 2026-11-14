"""Owner-scoped HTTP adapter for the existing M3 conversation workflow."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.v1.dependencies import CsrfPrincipalDep, PrincipalDep, ServicesDep
from app.repositories.conversations import ConversationThread, StoredMessage
from app.schemas.chat import (
    ConversationCreate,
    ConversationResponse,
    ConversationSummaryResponse,
    MessageCreate,
    MessageResponse,
    StoredMessageResponse,
)

router = APIRouter(prefix="/chat/sessions", tags=["chat"])


def _student_id(principal: PrincipalDep) -> str:
    if principal.role != "student" or not principal.student_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student role required.",
        )
    return principal.student_id


def _summary(thread: ConversationThread) -> ConversationSummaryResponse:
    return ConversationSummaryResponse(
        thread_id=thread.thread_id,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        revision=thread.revision,
        state=thread.state,
    )


def _message(message: StoredMessage) -> StoredMessageResponse:
    return StoredMessageResponse(
        message_id=message.message_id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
        sequence=message.sequence,
        response=message.response,
    )


@router.post("", response_model=ConversationSummaryResponse, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ConversationCreate,
    principal: CsrfPrincipalDep,
    services: ServicesDep,
) -> ConversationSummaryResponse:
    del payload
    student_id = _student_id(principal)
    thread = services.conversation_service.create(principal.user_id, student_id)
    return _summary(thread)


@router.get("", response_model=tuple[ConversationSummaryResponse, ...])
def list_conversations(
    principal: PrincipalDep,
    services: ServicesDep,
) -> tuple[ConversationSummaryResponse, ...]:
    _student_id(principal)
    return tuple(
        _summary(thread) for thread in services.conversations.list_for_owner(principal.user_id)
    )


@router.get("/{thread_id}", response_model=ConversationResponse)
def get_conversation(
    thread_id: str,
    principal: PrincipalDep,
    services: ServicesDep,
) -> ConversationResponse:
    _student_id(principal)
    try:
        thread = services.conversations.get(thread_id, principal.user_id)
        messages = services.conversations.messages(thread_id, principal.user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    return ConversationResponse(
        **_summary(thread).model_dump(),
        messages=tuple(_message(message) for message in messages),
    )


@router.post(
    "/{thread_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_message(
    thread_id: str,
    payload: MessageCreate,
    principal: CsrfPrincipalDep,
    services: ServicesDep,
) -> MessageResponse:
    student_id = _student_id(principal)
    scope = services.reading_scope(principal.user_id, student_id)
    try:
        response = services.conversation_service.handle_message(
            thread_id,
            principal.user_id,
            scope,
            payload.content,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conversation was updated concurrently; retry the request.",
        ) from exc
    return MessageResponse(thread_id=thread_id, response=response)
