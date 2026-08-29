"""Minimal Source -> Chunk -> retrieval -> grounded answer use cases."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from app.application.knowledge.service import ArtifactService
from app.application.model import GroundedAnswer
from app.domain.base.exceptions import ApplicationError, ErrorCode
from app.domain.knowledge import KnowledgeChunk
from app.ports.knowledge import ChunkRepository, EmbeddingPort, SourceDocumentRepository
from app.ports.model import ModelError, ModelPort, ModelRequest

RAG_PROMPT_VERSION = "rag-answer-v2"


@dataclass(frozen=True, slots=True)
class RetrievedEvidence:
    chunk_id: UUID
    source_id: UUID
    source_version: int
    locator: str
    excerpt: str
    score: float


@dataclass(frozen=True, slots=True)
class KnowledgeAnswer:
    query: str
    answer: str
    status: Literal["grounded", "unknown"]
    citations: tuple[RetrievedEvidence, ...]


class KnowledgeRagService:
    def __init__(
        self,
        *,
        artifacts: ArtifactService,
        sources: SourceDocumentRepository,
        chunks: ChunkRepository,
        embedding: EmbeddingPort,
        model: ModelPort | None = None,
    ) -> None:
        self.artifacts, self.sources, self.chunks = artifacts, sources, chunks
        self.embedding, self.model = embedding, model

    async def index_source(self, owner_id: UUID, source_id: UUID, *, chunk_size: int = 800) -> int:
        source = await self.sources.get_by_id(source_id)
        if source is None or source.owner_id != owner_id:
            raise ApplicationError("Source not found", error_code=ErrorCode.ENTITY_NOT_FOUND)
        download = await self.artifacts.download(owner_id, source.artifact_id)
        if download.artifact.version != source.artifact_version:
            raise ApplicationError("Source not found", error_code=ErrorCode.ENTITY_NOT_FOUND)
        try:
            text = download.data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ApplicationError(
                "Source content is not text", error_code=ErrorCode.INVALID_SOURCE_TYPE
            ) from exc
        pieces = _split_text(text, chunk_size)
        values = []
        for ordinal, piece in enumerate(pieces):
            values.append(
                KnowledgeChunk.create(
                    source=source,
                    ordinal=ordinal,
                    text=piece,
                    embedding=await self.embedding.embed(piece),
                    embedding_model=self.embedding.model,
                    embedding_version=self.embedding.version,
                )
            )
        await self.chunks.replace_for_source(source, values)
        await self.chunks.commit()
        return len(values)

    async def ask(
        self,
        owner_id: UUID,
        query: str,
        *,
        source_id: UUID | None = None,
        source_version: int | None = None,
        limit: int = 5,
    ) -> KnowledgeAnswer:
        normalized = query.strip()
        if not normalized:
            raise ApplicationError("Query is empty", error_code=ErrorCode.EMPTY_CONTENT)
        ranked = await self.chunks.search(
            owner_id=owner_id,
            query_embedding=await self.embedding.embed(normalized),
            source_id=source_id,
            source_version=source_version,
            limit=limit,
        )
        found = [item for item, _ in ranked]
        evidence = tuple(_evidence(item, score=score) for item, score in ranked)
        if not found or self.model is None:
            return KnowledgeAnswer(normalized, "unknown", "unknown", evidence)
        context = "\n\n".join(f"[{index}] {item.text}" for index, item in enumerate(found))
        try:
            result = await self.model.generate_structured(
                ModelRequest(
                    system_prompt=(
                        "Answer only from the supplied evidence. "
                        "Return unknown when it is insufficient. "
                        "Cite the zero-based local evidence indexes shown in this request; "
                        "do not duplicate or invent indexes."
                    ),
                    user_input=f"Question: {normalized}\nEvidence:\n{context}",
                    prompt_version=RAG_PROMPT_VERSION,
                    max_input_tokens=6000,
                    max_output_tokens=800,
                    temperature=0,
                ),
                GroundedAnswer,
            )
        except ModelError:
            return KnowledgeAnswer(normalized, "unknown", "unknown", evidence)
        by_context_index = {index: (item, score) for index, (item, score) in enumerate(ranked)}
        if (
            result.status != "grounded"
            or not result.citation_ordinals
            or len(set(result.citation_ordinals)) != len(result.citation_ordinals)
            or any(item not in by_context_index for item in result.citation_ordinals)
        ):
            return KnowledgeAnswer(normalized, "unknown", "unknown", evidence)
        citations = tuple(
            _evidence(by_context_index[item][0], score=by_context_index[item][1])
            for item in result.citation_ordinals
        )
        return KnowledgeAnswer(normalized, result.answer, "grounded", citations)


def _split_text(value: str, chunk_size: int) -> list[str]:
    if not 100 <= chunk_size <= 5000:
        raise ApplicationError("Chunk size is invalid", error_code=ErrorCode.INVALID_SOURCE_RANGE)
    normalized = "\n".join(
        line.strip() for line in value.replace("\r\n", "\n").splitlines()
    ).strip()
    return [
        normalized[index : index + chunk_size].strip()
        for index in range(0, len(normalized), chunk_size)
        if normalized[index : index + chunk_size].strip()
    ]


def _evidence(chunk: KnowledgeChunk, *, score: float) -> RetrievedEvidence:
    return RetrievedEvidence(
        chunk.id, chunk.source_id, chunk.source_version, chunk.locator, chunk.text[:500], score
    )


__all__ = ("GroundedAnswer", "KnowledgeAnswer", "KnowledgeRagService", "RetrievedEvidence")
