"""Course-scoped tutor over approved M2 evidence only."""

from __future__ import annotations

import re

from app.agents.answer_composer import AnswerComposer, OfflineAnswerComposer
from app.agents.models import AgentResponse, Citation, ConversationState
from app.domain.catalog import AcademicCatalog
from app.domain.models import Student
from app.ingestion.reading_models import VisualType
from app.retrieval.readings import Evidence, ReadingScope, Retriever

COURSE_CODE = re.compile(r"\b[A-Z]{2,5}\s*\d{3}\b", re.I)
PAGE = re.compile(r"\b(?:pdf\s+)?page\s+(\d+)\b", re.I)
FIGURE = re.compile(r"\bfigure\s+(\d+)\b", re.I)
EXACT = re.compile(r"\b(how many|how much|exact|value|according to (?:its|the) label)\b", re.I)
OPERATIONAL_NUCLEAR = re.compile(
    r"\b(?:calculate|derive|optimi[sz]e|design|build|construct|assemble)\b"
    r".{0,100}\b(?:nuclear weapon|atomic bomb|fissile|critical mass|implosion)\b"
    r"|\b(?:nuclear weapon|atomic bomb|fissile|critical mass|implosion)\b"
    r".{0,100}\b(?:calculate|derive|optimi[sz]e|design|build|construct|assemble)\b",
    re.IGNORECASE | re.DOTALL,
)
VISUALS: tuple[tuple[str, VisualType], ...] = (
    ("diagram", "figure"),
    ("figure", "figure"),
    ("chart", "chart"),
    ("graph", "chart"),
    ("plot", "chart"),
    ("table", "table"),
    ("equation", "equation"),
    ("formula", "equation"),
)


def _citation(evidence: Evidence) -> Citation:
    return Citation(
        document_title=evidence.document_title,
        document_id=evidence.document_id,
        course_code=evidence.course_code,
        pdf_page_number=evidence.page_number,
        chunk_id=evidence.chunk_id,
    )


def _visual_type(message: str) -> VisualType | None:
    lowered = message.lower()
    return next((kind for word, kind in VISUALS if word in lowered), None)


def _resolve_course(
    message: str,
    state: ConversationState,
    student: Student,
    catalog: AcademicCatalog,
    authorized_course_ids: frozenset[str],
) -> tuple[str | None, str | None]:
    explicit = COURSE_CODE.search(message)
    if explicit:
        course_id = re.sub(r"\s+", " ", explicit.group().upper())
        if catalog.maybe_course(course_id) and course_id in authorized_course_ids:
            return course_id, None
        return None, "That course is not in the authorized course context."
    if (
        state.active_course_id
        and state.active_course_id in authorized_course_ids
        and (
        re.search(r"\b(that|this|it|the reading|figure|diagram|page)\b", message, re.I)
        )
    ):
        return state.active_course_id, None
    lowered = message.lower()
    exact_matches = {
        document.course_id
        for document in catalog.reading_documents
        if document.course_id in authorized_course_ids and document.title.lower() in lowered
    }
    if len(exact_matches) == 1:
        return exact_matches.pop(), None
    matches = {
        document.course_id
        for document in catalog.reading_documents
        if document.course_id in authorized_course_ids
        and any(
            len(token) > 3 and token in lowered
            for token in re.findall(r"\w+", document.title.lower())
        )
    }
    if len(matches) == 1:
        return matches.pop(), None
    current_with_readings = tuple(
        sorted(
            (
                course_id
                for course_id in authorized_course_ids
                if catalog.course(course_id).reading_document_ids
            ),
            key=lambda course_id: (not student.is_current(course_id), course_id),
        )
    )
    if len(current_with_readings) == 1:
        return current_with_readings[0], None
    choices = ", ".join(current_with_readings)
    return None, f"Which current course do you mean? Available reading courses: {choices}."


def _document_id(
    course_id: str, state: ConversationState, catalog: AcademicCatalog
) -> str | None:
    if state.active_course_id == course_id and state.active_document_id:
        return state.active_document_id
    documents = catalog.course(course_id).reading_document_ids
    return documents[0] if len(documents) == 1 else None


def tutor(
    message: str,
    state: ConversationState,
    student: Student,
    catalog: AcademicCatalog,
    scope: ReadingScope,
    retriever: Retriever,
    composer: AnswerComposer | None = None,
) -> tuple[AgentResponse, ConversationState]:
    if OPERATIONAL_NUCLEAR.search(message):
        return (
            AgentResponse(
                status="unsupported",
                intent="tutor",
                text=(
                    "I can't help calculate, design, or optimize a nuclear weapon or "
                    "fissile-material configuration. I can offer a non-operational, "
                    "high-level explanation of the relevant physics when approved "
                    "course evidence is available."
                ),
            ),
            state.model_copy(update={"last_intent": "tutor"}),
        )
    course_id, clarification = _resolve_course(
        message, state, student, catalog, scope.course_ids
    )
    if course_id is None:
        return (
            AgentResponse(
                status="clarification_required",
                intent="tutor",
                text=clarification or "Which course do you mean?",
            ),
            state.model_copy(update={"last_intent": "tutor"}),
        )
    document_id = _document_id(course_id, state, catalog)
    if document_id is None:
        return (
            AgentResponse(
                status="clarification_required",
                intent="tutor",
                text="Which reading do you mean?",
            ),
            state.model_copy(update={"last_intent": "tutor", "active_course_id": course_id}),
        )

    visual_type = _visual_type(message)
    if visual_type:
        page_match = PAGE.search(message)
        figure_match = FIGURE.search(message)
        visual_result = retriever.resolve_visual(
            scope,
            course_id,
            document_id,
            page_number=int(page_match.group(1)) if page_match else None,
            visual_type=visual_type,
            label=f"Figure {figure_match.group(1)}" if figure_match else None,
            exact=bool(EXACT.search(message)),
        )
        next_state = state.model_copy(
            update={
                "last_intent": "tutor",
                "active_course_id": course_id,
                "active_document_id": document_id,
                "candidate_asset_ids": visual_result.candidate_asset_ids,
            }
        )
        if visual_result.status == "clarification_required":
            return (
                AgentResponse(
                    status="clarification_required",
                    intent="tutor",
                    text=visual_result.note or "Which visual do you mean?",
                ),
                next_state,
            )
        if visual_result.status != "ok" or visual_result.evidence is None:
            return (
                AgentResponse(
                    status="insufficient_evidence",
                    intent="tutor",
                    text=visual_result.note or "The approved source visual is unavailable.",
                ),
                next_state,
            )
        asset = visual_result.evidence.asset
        if figure_match and asset.label and asset.label.casefold() != (
            f"Figure {figure_match.group(1)}".casefold()
        ):
            return (
                AgentResponse(
                    status="insufficient_evidence",
                    intent="tutor",
                    text="The approved visual does not match the requested figure label.",
                ),
                next_state,
            )
        source_text = asset.source_transcription or asset.caption or asset.visual_description
        if not source_text:
            return (
                AgentResponse(
                    status="insufficient_evidence",
                    intent="tutor",
                    text=(
                        "The visual is approved, but no reviewed transcription "
                        "supports an answer."
                    ),
                ),
                next_state,
            )
        citation = Citation(
            document_title=visual_result.evidence.document_title,
            document_id=document_id,
            course_code=course_id,
            pdf_page_number=asset.pdf_page_number,
            asset_id=asset.asset_id,
            label=asset.label,
        )
        label = f", {asset.label}" if asset.label else ""
        response = AgentResponse(
            status="ok",
            intent="tutor",
            text=(
                f"According to the reviewed source visual: {source_text} "
                f"[{visual_result.evidence.document_title}, "
                f"PDF page {asset.pdf_page_number}{label}]."
            ),
            citations=(citation,),
        )
        return (
            response,
            next_state.model_copy(
                update={"last_asset_id": asset.asset_id, "candidate_asset_ids": ()}
            ),
        )

    search_result = retriever.search(scope, course_id, message)
    next_state = state.model_copy(
        update={
            "last_intent": "tutor",
            "active_course_id": course_id,
            "active_document_id": document_id,
            "candidate_asset_ids": (),
        }
    )
    if search_result.status != "ok" or not search_result.evidence:
        return (
            AgentResponse(
                status="insufficient_evidence",
                intent="tutor",
                text=(
                    search_result.note
                    or "The approved reading evidence does not answer that question."
                ),
            ),
            next_state,
        )
    evidence = search_result.evidence[:5]
    try:
        composed = (composer or OfflineAnswerComposer()).compose(message, evidence)
    except ValueError:
        return (
            AgentResponse(
                status="insufficient_evidence",
                intent="tutor",
                text="The approved evidence could not be composed into a grounded answer.",
            ),
            next_state,
        )
    if any(claim.evidence_index >= len(evidence) for claim in composed.claims):
        return (
            AgentResponse(
                status="insufficient_evidence",
                intent="tutor",
                text="The answer composer returned an invalid evidence reference.",
            ),
            next_state,
        )
    cited_evidence = tuple(evidence[claim.evidence_index] for claim in composed.claims)
    claims = " ".join(
        f"{claim.text} [{source.document_title}, PDF page {source.page_number}]."
        for claim, source in zip(composed.claims, cited_evidence, strict=True)
    )
    return (
        AgentResponse(
            status="ok",
            intent="tutor",
            text=claims,
            citations=tuple(_citation(item) for item in cited_evidence),
        ),
        next_state,
    )
