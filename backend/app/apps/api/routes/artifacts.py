"""Authenticated Artifact and SourceDocument API."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, Request, Response, UploadFile, status
from pydantic import BaseModel, Field

from app.application.knowledge import ArtifactService, CreateSourceCommand, UploadArtifactCommand
from app.apps.api.dependencies import (
    get_artifact_repository,
    get_artifact_storage,
    get_audit_event_repository,
    get_current_user,
    get_source_document_repository,
)
from app.domain.identity import User
from app.domain.knowledge import Artifact, ArtifactKind, ArtifactStatus, SourceDocument, SourceKind
from app.ports.governance import AuditEventRepository
from app.ports.knowledge import ArtifactRepository, ArtifactStorage, SourceDocumentRepository

router = APIRouter(tags=["artifacts"])


class ArtifactResponse(BaseModel):
    id: UUID
    version: int
    kind: ArtifactKind
    content_type: str
    size_bytes: int
    sha256: str
    status: ArtifactStatus
    created_at: datetime
    deleted_at: datetime | None

    @classmethod
    def from_domain(cls, value: Artifact) -> "ArtifactResponse":
        return cls.model_validate(value, from_attributes=True)


class CreateSourceRequest(BaseModel):
    artifact_id: UUID
    source_kind: SourceKind
    acquisition_method: str = Field(min_length=1, max_length=100)
    license_note: str = Field(min_length=1, max_length=500)
    locator: str | None = Field(default=None, max_length=2000)
    acquired_at: datetime | None = None
    published_at: datetime | None = None


class SourceResponse(BaseModel):
    id: UUID
    version: int
    artifact_id: UUID
    artifact_version: int
    source_kind: SourceKind
    acquisition_method: str
    license_note: str
    locator: str | None
    acquired_at: datetime
    published_at: datetime | None
    content_sha256: str
    created_at: datetime

    @classmethod
    def from_domain(cls, value: SourceDocument) -> "SourceResponse":
        return cls.model_validate(value, from_attributes=True)


def _service(
    request: Request,
    user: User,
    artifacts: ArtifactRepository,
    sources: SourceDocumentRepository,
    storage: ArtifactStorage,
    audit_events: AuditEventRepository,
) -> ArtifactService:
    del user
    settings = request.app.state.settings
    return ArtifactService(
        artifacts,
        sources,
        storage,
        audit_events,
        max_size_bytes=settings.artifact_max_size_bytes,
        allowed_content_types=settings.allowed_artifact_content_types,
    )


@router.post("/artifacts", response_model=ArtifactResponse, status_code=status.HTTP_201_CREATED)
async def upload_artifact(
    request: Request,
    file: Annotated[UploadFile, File()],
    kind: Annotated[ArtifactKind, Form()] = ArtifactKind.SOURCE,
    generator_version: Annotated[str | None, Form(max_length=100)] = None,
    generation_identity: Annotated[str | None, Form(min_length=64, max_length=64)] = None,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=255)
    ] = "",
    user: User = Depends(get_current_user),
    artifacts: ArtifactRepository = Depends(get_artifact_repository),
    sources: SourceDocumentRepository = Depends(get_source_document_repository),
    storage: ArtifactStorage = Depends(get_artifact_storage),
    audit_events: AuditEventRepository = Depends(get_audit_event_repository),
) -> ArtifactResponse:
    service = _service(request, user, artifacts, sources, storage, audit_events)
    data = await _read_limited(file, request.app.state.settings.artifact_max_size_bytes)
    value = await service.upload(
        UploadArtifactCommand(
            owner_id=user.id,
            kind=kind,
            content_type=file.content_type or "application/octet-stream",
            data=data,
            idempotency_key=idempotency_key,
            generator_version=generator_version,
            generation_identity=generation_identity,
        )
    )
    return ArtifactResponse.from_domain(value)


@router.get("/artifacts/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(
    request: Request,
    artifact_id: UUID,
    user: User = Depends(get_current_user),
    artifacts: ArtifactRepository = Depends(get_artifact_repository),
    sources: SourceDocumentRepository = Depends(get_source_document_repository),
    storage: ArtifactStorage = Depends(get_artifact_storage),
    audit_events: AuditEventRepository = Depends(get_audit_event_repository),
) -> ArtifactResponse:
    return ArtifactResponse.from_domain(
        await _service(request, user, artifacts, sources, storage, audit_events).get(
            user.id, artifact_id
        )
    )


@router.get("/artifacts/{artifact_id}/content")
async def download_artifact(
    request: Request,
    artifact_id: UUID,
    user: User = Depends(get_current_user),
    artifacts: ArtifactRepository = Depends(get_artifact_repository),
    sources: SourceDocumentRepository = Depends(get_source_document_repository),
    storage: ArtifactStorage = Depends(get_artifact_storage),
    audit_events: AuditEventRepository = Depends(get_audit_event_repository),
) -> Response:
    result = await _service(request, user, artifacts, sources, storage, audit_events).download(
        user.id, artifact_id
    )
    return Response(
        content=result.data,
        media_type=result.artifact.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="artifact-{result.artifact.id}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/artifacts/{artifact_id}", response_model=ArtifactResponse)
async def delete_artifact(
    request: Request,
    artifact_id: UUID,
    user: User = Depends(get_current_user),
    artifacts: ArtifactRepository = Depends(get_artifact_repository),
    sources: SourceDocumentRepository = Depends(get_source_document_repository),
    storage: ArtifactStorage = Depends(get_artifact_storage),
    audit_events: AuditEventRepository = Depends(get_audit_event_repository),
) -> ArtifactResponse:
    return ArtifactResponse.from_domain(
        await _service(request, user, artifacts, sources, storage, audit_events).delete(
            user.id, artifact_id
        )
    )


@router.post("/sources", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def create_source(
    request: Request,
    payload: CreateSourceRequest,
    user: User = Depends(get_current_user),
    artifacts: ArtifactRepository = Depends(get_artifact_repository),
    sources: SourceDocumentRepository = Depends(get_source_document_repository),
    storage: ArtifactStorage = Depends(get_artifact_storage),
    audit_events: AuditEventRepository = Depends(get_audit_event_repository),
) -> SourceResponse:
    source = await _service(request, user, artifacts, sources, storage, audit_events).create_source(
        CreateSourceCommand(owner_id=user.id, **payload.model_dump())
    )
    return SourceResponse.from_domain(source)


async def _read_limited(file: UploadFile, max_size: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(min(64 * 1024, max_size + 1 - total)):
        total += len(chunk)
        if total > max_size:
            from app.domain.base.exceptions import ApplicationError

            raise ApplicationError("Artifact size is invalid", error_code="artifact_too_large")
        chunks.append(chunk)
    return b"".join(chunks)


@router.get("/sources/{source_id}", response_model=SourceResponse)
async def get_source(
    request: Request,
    source_id: UUID,
    user: User = Depends(get_current_user),
    artifacts: ArtifactRepository = Depends(get_artifact_repository),
    sources: SourceDocumentRepository = Depends(get_source_document_repository),
    storage: ArtifactStorage = Depends(get_artifact_storage),
    audit_events: AuditEventRepository = Depends(get_audit_event_repository),
) -> SourceResponse:
    return SourceResponse.from_domain(
        await _service(request, user, artifacts, sources, storage, audit_events).get_source(
            user.id, source_id
        )
    )
