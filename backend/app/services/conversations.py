"""M3 turn orchestration with fresh academic reads and compact checkpoints."""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from app.agents.academic_planner import plan, requested_unit_cap
from app.agents.answer_composer import AnswerComposer, OfflineAnswerComposer
from app.agents.course_tutor import tutor
from app.agents.models import AgentResponse, TraceEvent
from app.agents.supervisor import route_intent
from app.ingestion.dataset import AcademicDataset
from app.repositories.conversations import ConversationRepository, ConversationThread
from app.retrieval.readings import ReadingScope, Retriever


class ConversationService:
    def __init__(
        self,
        repository: ConversationRepository,
        dataset_loader: Callable[[], AcademicDataset],
        retriever: Retriever,
        composer: AnswerComposer | None = None,
    ):
        self.repository = repository
        self.dataset_loader = dataset_loader
        self.retriever = retriever
        self.composer = composer or OfflineAnswerComposer()

    def create(self, owner_user_id: str, authorized_student_id: str) -> ConversationThread:
        # Validate against the current source rather than persisting a student snapshot.
        self.dataset_loader().student(authorized_student_id)
        return self.repository.create(owner_user_id, authorized_student_id)

    def handle_message(
        self,
        thread_id: str,
        owner_user_id: str,
        scope: ReadingScope,
        message: str,
    ) -> AgentResponse:
        if not message.strip() or len(message) > 4000:
            raise ValueError("message must have 1-4000 characters")
        if scope.principal_id != owner_user_id:
            raise PermissionError("reading scope principal does not own conversation")
        thread = self.repository.get(thread_id, owner_user_id)
        dataset = self.dataset_loader()
        student = dataset.student(thread.authorized_student_id)
        intent = route_intent(message, thread.state)
        supervisor_trace = TraceEvent(
            trace_id=f"trace-{uuid4()}",
            agent_name="supervisor",
            status="ok" if intent != "unsupported" else "unsupported",
            metadata={"intent": intent},
        )

        if intent == "planner":
            cap = requested_unit_cap(message)
            effective_preference = cap if cap is not None else thread.state.planning_unit_cap
            if effective_preference is not None and effective_preference <= 0:
                response = AgentResponse(
                    status="clarification_required",
                    intent="planner",
                    text="Please specify a positive unit cap.",
                )
                state = thread.state.model_copy(update={"last_intent": "planner"})
            else:
                response = plan(
                    student,
                    dataset.catalog,
                    unit_cap=effective_preference,
                    catalogue_version=dataset.catalogue_source.source_version,
                    student_record_version=dataset.students_source.source_version,
                )
                state = thread.state.model_copy(
                    update={"last_intent": "planner", "planning_unit_cap": effective_preference}
                )
        elif intent == "tutor":
            response, state = tutor(
                message,
                thread.state,
                student,
                dataset.catalog,
                scope,
                self.retriever,
                self.composer,
            )
        else:
            response = AgentResponse(
                status="unsupported",
                intent="unsupported",
                text=(
                    "I can help with the supplied course readings or the verified "
                    "Spring 2027 academic plan. The provided data does not support this request."
                ),
            )
            state = thread.state.model_copy(update={"last_intent": "unsupported"})

        traces = [supervisor_trace]
        if intent in ("planner", "tutor"):
            traces.append(
                TraceEvent(
                    trace_id=f"trace-{uuid4()}",
                    agent_name=intent,
                    status=response.status,
                    metadata={"intent": intent},
                )
            )
        response = response.model_copy(
            update={"trace_ids": tuple(trace.trace_id for trace in traces)}
        )
        self.repository.append_turn(thread, message, response, state, traces=tuple(traces))
        return response
