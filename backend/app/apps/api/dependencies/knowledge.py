"""Knowledge API composition dependencies."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.knowledge import ArtifactService, KnowledgeRagService
from app.apps.api.dependencies.common import get_current_user, get_session, get_settings
from app.apps.api.dependencies.decision import get_model_port
from app.apps.api.dependencies.governance import get_audit_event_repository
from app.domain.identity import User
from app.infrastructure.config import Settings
from app.infrastructure.database import (
    SqlAlchemyArtifactRepository,
    SqlAlchemyChunkRepository,
    SqlAlchemySourceDocumentRepository,
)
from app.infrastructure.embedding import DeterministicEmbeddingAdapter
from app.infrastructure.object_storage import create_minio_storage
from app.ports.governance import AuditEventRepository
from app.ports.knowledge import (
    ArtifactRepository,
    ArtifactStorage,
    ChunkRepository,
    SourceDocumentRepository,
)
from app.ports.model import ModelPort


def get_artifact_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ArtifactRepository:
    return SqlAlchemyArtifactRepository(session, user.id)


def get_source_document_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> SourceDocumentRepository:
    return SqlAlchemySourceDocumentRepository(session, user.id)


def get_artifact_storage(settings: Settings = Depends(get_settings)) -> ArtifactStorage:
    return create_minio_storage(
        endpoint=settings.artifact_storage_endpoint,
        access_key=settings.artifact_storage_access_key,
        secret_key=settings.artifact_storage_secret_key,
        bucket=settings.artifact_storage_bucket,
        secure=settings.artifact_storage_secure,
    )


def get_chunk_repository(session: AsyncSession = Depends(get_session)) -> ChunkRepository:
    return SqlAlchemyChunkRepository(session)


def get_knowledge_rag_service(
    settings: Settings = Depends(get_settings),
    artifacts: ArtifactRepository = Depends(get_artifact_repository),
    sources: SourceDocumentRepository = Depends(get_source_document_repository),
    storage: ArtifactStorage = Depends(get_artifact_storage),
    audits: AuditEventRepository = Depends(get_audit_event_repository),
    chunks: ChunkRepository = Depends(get_chunk_repository),
    model: ModelPort = Depends(get_model_port),
) -> KnowledgeRagService:
    service = ArtifactService(
        artifacts,
        sources,
        storage,
        audits,
        max_size_bytes=settings.artifact_max_size_bytes,
        allowed_content_types=settings.allowed_artifact_content_types,
    )
    return KnowledgeRagService(
        artifacts=service,
        sources=sources,
        chunks=chunks,
        embedding=DeterministicEmbeddingAdapter(),
        model=model,
    )
