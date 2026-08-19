"""Minimal authenticated RAG indexing and ask API."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.knowledge import ArtifactService, KnowledgeRagService
from app.apps.api.dependencies.common import get_current_user, get_session, get_settings
from app.apps.api.dependencies.decision import get_model_port
from app.apps.api.dependencies.governance import get_audit_event_repository
from app.apps.api.dependencies.knowledge import (
    get_artifact_repository,
    get_artifact_storage,
    get_source_document_repository,
)
from app.domain.identity import User
from app.infrastructure.config import Settings
from app.infrastructure.database import SqlAlchemyChunkRepository
from app.infrastructure.embedding import DeterministicEmbeddingAdapter
from app.ports.governance import AuditEventRepository
from app.ports.knowledge import (
    ArtifactRepository,
    ArtifactStorage,
    ChunkRepository,
    SourceDocumentRepository,
)
from app.ports.model import ModelPort

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def _get_chunk_repository(
    session: AsyncSession = Depends(get_session),
) -> ChunkRepository:
    return SqlAlchemyChunkRepository(session)


class IndexResponse(BaseModel):
    source_id: UUID
    chunks: int
    embedding_model: str
    embedding_version: str
    embedding_dimension: int


class EvidenceResponse(BaseModel):
    chunk_id: UUID
    source_id: UUID
    source_version: int
    locator: str
    excerpt: str
    score: float


class AskRequest(BaseModel):
    query: Annotated[str, Field(min_length=1, max_length=2000)]
    source_id: UUID | None = None
    source_version: int | None = Field(default=None, ge=1)
    limit: int = Field(default=5, ge=1, le=20)


class AskResponse(BaseModel):
    query: str
    answer: str
    status: str
    citations: list[EvidenceResponse]


def _service(
    settings: Settings,
    user: User,
    session: AsyncSession,
    artifacts: ArtifactRepository,
    sources: SourceDocumentRepository,
    storage: ArtifactStorage,
    audits: AuditEventRepository,
    chunks: ChunkRepository,
    model: ModelPort | None,
) -> KnowledgeRagService:
    artifact_service = ArtifactService(
        artifacts,
        sources,
        storage,
        audits,
        max_size_bytes=settings.artifact_max_size_bytes,
        allowed_content_types=settings.allowed_artifact_content_types,
    )
    del user, session
    return KnowledgeRagService(
        artifacts=artifact_service,
        sources=sources,
        chunks=chunks,
        embedding=DeterministicEmbeddingAdapter(),
        model=model,
    )


@router.post("/sources/{source_id}/index", response_model=IndexResponse)
async def index_source(
    source_id: UUID,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
    artifacts: ArtifactRepository = Depends(get_artifact_repository),
    sources: SourceDocumentRepository = Depends(get_source_document_repository),
    storage: ArtifactStorage = Depends(get_artifact_storage),
    audits: AuditEventRepository = Depends(get_audit_event_repository),
    chunks: ChunkRepository = Depends(_get_chunk_repository),
) -> IndexResponse:
    # Settings is resolved from request state by the dependency override below.
    service = _service(settings, user, session, artifacts, sources, storage, audits, chunks, None)
    count = await service.index_source(user.id, source_id)
    return IndexResponse(
        source_id=source_id,
        chunks=count,
        embedding_model=service.embedding.model,
        embedding_version=service.embedding.version,
        embedding_dimension=service.embedding.dimension,
    )


@router.post("/ask", response_model=AskResponse)
async def ask_knowledge(
    payload: AskRequest,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
    artifacts: ArtifactRepository = Depends(get_artifact_repository),
    sources: SourceDocumentRepository = Depends(get_source_document_repository),
    storage: ArtifactStorage = Depends(get_artifact_storage),
    audits: AuditEventRepository = Depends(get_audit_event_repository),
    chunks: ChunkRepository = Depends(_get_chunk_repository),
    model: ModelPort = Depends(get_model_port),
) -> AskResponse:
    service = _service(settings, user, session, artifacts, sources, storage, audits, chunks, model)
    result = await service.ask(user.id, **payload.model_dump())
    return AskResponse(
        query=result.query,
        answer=result.answer,
        status=result.status,
        citations=[
            EvidenceResponse.model_validate(item, from_attributes=True) for item in result.citations
        ],
    )
