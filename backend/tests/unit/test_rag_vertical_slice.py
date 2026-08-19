from datetime import datetime, timezone
from uuid import uuid4

import pytest
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


def _source() -> SourceDocument:
    artifact = Artifact.pending(
        owner_id=uuid4(),
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
