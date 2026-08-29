from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.application.knowledge import KnowledgeRagService
from app.domain.knowledge import (
    Artifact,
    ArtifactKind,
    KnowledgeChunk,
    SourceDocument,
    SourceKind,
)
from app.infrastructure.embedding import DeterministicEmbeddingAdapter


class _ArtifactService:
    async def download(self, owner_id, artifact_id):
        raise AssertionError("indexing is not used by answer contract tests")


class _Chunks:
    async def search(self, **kwargs):
        return []

    async def replace_for_source(self, source, chunks):
        raise AssertionError("not used")

    async def commit(self):
        raise AssertionError("not used")


class _RetrievedChunks:
    def __init__(self, ranked):
        self.ranked = ranked

    async def search(self, **kwargs):
        return self.ranked


class _GroundedModel:
    def __init__(self, citation_indexes):
        self.citation_indexes = citation_indexes
        self.request = None

    async def generate_structured(self, request, output_type):
        self.request = request
        return output_type(
            answer="来自证据的回答",
            status="grounded",
            citation_indexes=self.citation_indexes,
        )


def _source(owner_id=None) -> SourceDocument:
    owner_id = owner_id or uuid4()
    artifact = Artifact.pending(
        owner_id=owner_id,
        kind=ArtifactKind.SOURCE,
        content_type="text/plain",
        size_bytes=10,
        sha256="a" * 64,
        idempotency_key="rag-test",
        now=datetime.now(timezone.utc),
    ).publish("object")
    return SourceDocument.create(
        artifact=artifact,
        source_kind=SourceKind.MANUAL,
        acquisition_method="test",
        license_note="owned",
        now=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_embedding_is_deterministic_and_normalized() -> None:
    adapter = DeterministicEmbeddingAdapter()
    first = await adapter.embed("same text")
    second = await adapter.embed("same text")
    assert first == second
    assert len(first) == adapter.dimension
    assert sum(value * value for value in first) == pytest.approx(1.0)


def test_chunk_keeps_exact_source_identity_and_locator() -> None:
    source = _source()
    chunk = KnowledgeChunk.create(
        source=source,
        ordinal=2,
        text="  hello\nworld  ",
        embedding=(1.0, 0.0),
        embedding_model="model",
        embedding_version="v1",
    )
    assert chunk.source_id == source.id
    assert chunk.source_version == source.version
    assert chunk.locator == "chunk-2"
    assert chunk.text == "hello\nworld"
    assert chunk.embedding_dimension == 2


@pytest.mark.asyncio
async def test_empty_retrieval_is_explicit_unknown() -> None:
    from app.application.knowledge import KnowledgeRagService

    service = KnowledgeRagService(
        artifacts=_ArtifactService(),
        sources=object(),
        chunks=_Chunks(),
        embedding=DeterministicEmbeddingAdapter(),
        model=None,
    )
    result = await service.ask(uuid4(), "where is the evidence?")
    assert result.status == "unknown"
    assert result.answer == "unknown"
    assert result.citations == ()


@pytest.mark.asyncio
async def test_citations_use_request_local_indexes_across_sources() -> None:
    owner_id = uuid4()
    first_source = _source(owner_id)
    second_source = _source(owner_id)
    first = KnowledgeChunk.create(
        source=first_source,
        ordinal=0,
        text="第一来源证据",
        embedding=(1.0, 0.0),
        embedding_model="model",
        embedding_version="v1",
    )
    second = KnowledgeChunk.create(
        source=second_source,
        ordinal=0,
        text="第二来源证据",
        embedding=(0.0, 1.0),
        embedding_model="model",
        embedding_version="v1",
    )
    model = _GroundedModel([0, 1])
    service = KnowledgeRagService(
        artifacts=_ArtifactService(),
        sources=object(),
        chunks=_RetrievedChunks([(first, 0.9), (second, 0.8)]),
        embedding=DeterministicEmbeddingAdapter(),
        model=model,
    )

    result = await service.ask(owner_id, "查询证据")

    assert result.status == "grounded"
    assert [item.chunk_id for item in result.citations] == [first.id, second.id]
    assert model.request is not None
    assert "[0] 第一来源证据" in model.request.user_input
    assert "[1] 第二来源证据" in model.request.user_input


@pytest.mark.asyncio
@pytest.mark.parametrize("citation_indexes", ([0, 0], [2]))
async def test_invalid_local_citation_indexes_return_unknown(citation_indexes) -> None:
    owner_id = uuid4()
    source = _source(owner_id)
    chunk = KnowledgeChunk.create(
        source=source,
        ordinal=0,
        text="唯一来源证据",
        embedding=(1.0, 0.0),
        embedding_model="model",
        embedding_version="v1",
    )
    service = KnowledgeRagService(
        artifacts=_ArtifactService(),
        sources=object(),
        chunks=_RetrievedChunks([(chunk, 0.9)]),
        embedding=DeterministicEmbeddingAdapter(),
        model=_GroundedModel(citation_indexes),
    )

    result = await service.ask(owner_id, "查询证据")

    assert result.status == "unknown"
    assert result.answer == "unknown"
    assert [item.chunk_id for item in result.citations] == [chunk.id]
