"""Knowledge & Evidence application ports."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.base.exceptions import InfrastructureError
from app.domain.knowledge import Artifact, KnowledgeChunk, SourceDocument


@dataclass(frozen=True, slots=True)
class StoredObject:
    data: bytes
    content_type: str


@dataclass(frozen=True, slots=True)
class StoredObjectInfo:
    object_key: str
    last_modified: datetime


class ArtifactStorageError(InfrastructureError):
    """Known failure raised by an ArtifactStorage adapter."""


class ArtifactRepository(Protocol):
    async def get_by_id(self, artifact_id: UUID) -> Artifact | None: ...
    async def get_by_idempotency_key(self, key: str) -> Artifact | None: ...
    async def add(self, artifact: Artifact) -> Artifact: ...
    async def update(self, artifact: Artifact) -> Artifact: ...
    async def list_retryable(self, *, limit: int) -> list[Artifact]: ...
    async def list_object_keys(self) -> set[str]: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


class SourceDocumentRepository(Protocol):
    async def add(self, source: SourceDocument) -> SourceDocument: ...
    async def get_by_id(self, source_id: UUID) -> SourceDocument | None: ...
    async def get_by_identity(self, source_id: UUID, version: int) -> SourceDocument | None: ...
    async def commit(self) -> None: ...


class EmbeddingPort(Protocol):
    model: str
    version: str
    dimension: int

    async def embed(self, text: str) -> tuple[float, ...]: ...


class ChunkRepository(Protocol):
    async def replace_for_source(
        self, source: SourceDocument, chunks: list[KnowledgeChunk]
    ) -> None: ...

    async def search(
        self,
        *,
        owner_id: UUID,
        query_embedding: tuple[float, ...],
        embedding_model: str,
        embedding_version: str,
        embedding_dimension: int,
        source_id: UUID | None = None,
        source_version: int | None = None,
        limit: int = 5,
    ) -> list[tuple[KnowledgeChunk, float]]: ...

    async def commit(self) -> None: ...


class ArtifactStorage(Protocol):
    async def put(self, *, object_key: str, data: bytes, content_type: str) -> None: ...
    async def get(self, *, object_key: str) -> StoredObject: ...
    async def delete(self, *, object_key: str) -> None: ...
    async def list(self) -> list[StoredObjectInfo]: ...
