"""Owner-scoped HTTP adapter for the existing M3 conversation workflow."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.agents.models import Citation
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
from app.schemas.citations import CitationEvidenceResponse

router = APIRouter(prefix="/chat/sessions", tags=["chat"])


def _thread_citations(thread_id: str, owner_id: str, services: ServicesDep) -> tuple[Citation, ...]:
    messages = services.conversations.messages(thread_id, owner_id)
    return tuple(
        citation
        for message in messages
        if message.response
        for citation in message.response.citations
    )


def _student_id(principal: PrincipalDep) -> str:
    if principal.role != "student" or not principal.student_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student role required.",
        )
    return principal.student_id


def _owned_thread(
    thread_id: str,
    principal: PrincipalDep,
    services: ServicesDep,
) -> ConversationThread:
    try:
        thread = services.conversations.get(thread_id, principal.user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    if thread.authorized_student_id != _student_id(principal):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return thread


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
        thread, messages = services.conversations.get_with_messages(
            thread_id, principal.user_id
        )
        if thread.authorized_student_id != principal.student_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
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
    _owned_thread(thread_id, principal, services)
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


@router.get(
    "/{thread_id}/citations/{chunk_id}",
    response_model=CitationEvidenceResponse,
)
def get_citation(
    thread_id: str,
    chunk_id: str,
    principal: PrincipalDep,
    services: ServicesDep,
) -> CitationEvidenceResponse:
    student_id = _student_id(principal)
    try:
        _owned_thread(thread_id, principal, services)
        citations = _thread_citations(thread_id, principal.user_id, services)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    citation = next(
        (item for item in citations if item.chunk_id == chunk_id),
        None,
    )
    if citation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    scope = services.reading_scope(principal.user_id, student_id)
    try:
        evidence = services.retriever.resolve_citation(
            scope,
            citation.course_code,
            chunk_id,
        )
    except (PermissionError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    return CitationEvidenceResponse(
        document_title=evidence.document_title,
        document_id=evidence.document_id,
        course_code=evidence.course_code,
        page_number=evidence.page_number,
        section=evidence.section,
        excerpt=evidence.excerpt,
        chunk_id=evidence.chunk_id,
        source_checksum=evidence.source_checksum,
        ingestion_version=evidence.ingestion_version,
        extraction_method=evidence.extraction_method,
    )


@router.get("/{thread_id}/assets/{asset_id}")
def get_visual_asset(
    thread_id: str,
    asset_id: str,
    principal: PrincipalDep,
    services: ServicesDep,
) -> FileResponse:
    student_id = _student_id(principal)
    try:
        _owned_thread(thread_id, principal, services)
        citations = _thread_citations(thread_id, principal.user_id, services)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    citation = next((item for item in citations if item.asset_id == asset_id), None)
    if citation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    scope = services.reading_scope(principal.user_id, student_id)
    try:
        visual = services.retriever.resolve_visual(
            scope,
            citation.course_code,
            citation.document_id,
            asset_id=asset_id,
        )
    except (PermissionError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    if visual.status != "ok" or visual.evidence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return FileResponse(
        visual.evidence.crop_path,
        media_type="image/png",
        filename=f"{asset_id}.png",
        content_disposition_type="inline",
        headers={"Cache-Control": "private, no-store"},
    )


@router.get("/{thread_id}/documents/{document_id}/pages/{page_number}")
def get_cited_page(
    thread_id: str,
    document_id: str,
    page_number: int,
    principal: PrincipalDep,
    services: ServicesDep,
) -> FileResponse:
    """Serve a rendered page only when the thread already cites that document."""

    student_id = _student_id(principal)
    try:
        _owned_thread(thread_id, principal, services)
        citations = _thread_citations(thread_id, principal.user_id, services)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    if not any(item.document_id == document_id for item in citations):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    scope = services.reading_scope(principal.user_id, student_id)
    try:
        path = services.retriever.resolve_page(scope, document_id, page_number)
    except (PermissionError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    return FileResponse(
        path,
        media_type="image/png",
        filename=f"{document_id}-p{page_number}.png",
        content_disposition_type="inline",
        headers={"Cache-Control": "private, no-store"},
    )
