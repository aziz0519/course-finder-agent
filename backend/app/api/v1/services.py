"""Application services shared by the M4 HTTP layer."""

from __future__ import annotations

from dataclasses import dataclass

from app.auth.local_adapter import LocalAuthService
from app.core.config import Settings
from app.ingestion.dataset import AcademicDataset, load_dataset
from app.repositories.conversations import ConversationRepository
from app.repositories.readings import ReadingRepository
from app.retrieval.readings import LocalRetriever, ReadingScope
from app.services.conversations import ConversationService
from app.services.ingestion_jobs import IngestionJobService


@dataclass(frozen=True)
class ApiServices:
    settings: Settings
    auth: LocalAuthService
    conversations: ConversationRepository
    readings: ReadingRepository
    conversation_service: ConversationService
    ingestion_jobs: IngestionJobService

    @classmethod
    def create(cls, settings: Settings) -> ApiServices:
        settings.processed_dir.mkdir(parents=True, exist_ok=True)
        conversations = ConversationRepository(settings.processed_dir / "conversations.sqlite3")
        readings = ReadingRepository(settings.processed_dir / "readings")
        return cls(
            settings=settings,
            auth=LocalAuthService(settings),
            conversations=conversations,
            readings=readings,
            conversation_service=ConversationService(
                conversations,
                lambda: load_dataset(settings.data_root),
                LocalRetriever(readings),
            ),
            ingestion_jobs=IngestionJobService(settings.data_root, readings),
        )

    def dataset(self) -> AcademicDataset:
        """Re-read authoritative academic sources for every request."""

        return load_dataset(self.settings.data_root)

    def reading_scope(self, principal_id: str, student_id: str) -> ReadingScope:
        dataset = self.dataset()
        student = dataset.student(student_id)
        course_ids = frozenset(student.current_course_ids)
        document_ids = frozenset(
            document.document_id
            for document in dataset.catalog.reading_documents
            if document.course_id in course_ids
        )
        return ReadingScope(
            principal_id=principal_id,
            course_ids=course_ids,
            document_ids=document_ids,
        )
