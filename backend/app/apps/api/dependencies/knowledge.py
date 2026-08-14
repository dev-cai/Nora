"""Knowledge API composition dependencies."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.api.dependencies.common import get_current_user, get_session, get_settings
from app.domain.identity import User
from app.infrastructure.config import Settings
from app.infrastructure.database import (
    SqlAlchemyArtifactRepository,
    SqlAlchemySourceDocumentRepository,
)
from app.infrastructure.object_storage import create_minio_storage
from app.ports.knowledge import ArtifactRepository, ArtifactStorage, SourceDocumentRepository


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
