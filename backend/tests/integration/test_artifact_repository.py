"""Artifact and SourceDocument PostgreSQL ownership tests."""

import hashlib

import pytest
from app.domain.identity import User
from app.domain.knowledge import Artifact, ArtifactKind, SourceDocument, SourceKind
from app.infrastructure.database import (
    SqlAlchemyArtifactRepository,
    SqlAlchemySourceDocumentRepository,
    SqlAlchemyUserRepository,
)
from sqlalchemy.ext.asyncio import AsyncSession


async def _user(session: AsyncSession, name: str) -> User:
    user = User.create(username=name, email=f"{name}@example.com", password_hash="hash")
    await SqlAlchemyUserRepository(session).add(user)
    await session.commit()
    return user


@pytest.mark.asyncio
async def test_artifact_and_source_are_versioned_and_user_scoped(session: AsyncSession) -> None:
    alice = await _user(session, "artifact-alice")
    bob = await _user(session, "artifact-bob")
    repository = SqlAlchemyArtifactRepository(session, alice.id)
    artifact = Artifact.pending(
        owner_id=alice.id,
        kind=ArtifactKind.SOURCE,
        content_type="text/plain",
        size_bytes=4,
        sha256=hashlib.sha256(b"data").hexdigest(),
        idempotency_key="key-1",
    )
    await repository.add(artifact)
    await repository.commit()
    available = artifact.publish(f"{alice.id}/{artifact.id}/1/random")
    await repository.update(available)
    await repository.commit()

    assert await repository.get_by_id(artifact.id) == available
    assert await SqlAlchemyArtifactRepository(session, bob.id).get_by_id(artifact.id) is None

    source = SourceDocument.create(
        artifact=available,
        source_kind=SourceKind.FILE,
        acquisition_method="user_upload",
        license_note="user supplied",
    )
    source_repository = SqlAlchemySourceDocumentRepository(session, alice.id)
    await source_repository.add(source)
    await source_repository.commit()
    assert await source_repository.get_by_id(source.id) == source
    assert await SqlAlchemySourceDocumentRepository(session, bob.id).get_by_id(source.id) is None
