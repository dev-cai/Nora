"""D-021 JD ImportSession/Draft API。"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, StringConstraints

from app.agent_runtime import JdImportAgent
from app.application.imports import (
    ConfirmJdImportCommand,
    CreateJdImportCommand,
    EditJdImportDraftCommand,
    JdImportDraftContent,
    JdImportService,
)
from app.apps.api.dependencies.common import get_current_user
from app.apps.api.dependencies.decision import get_jd_import_agent
from app.apps.api.dependencies.governance import get_audit_event_repository
from app.apps.api.dependencies.opportunity import (
    get_import_repository,
    get_job_posting_repository,
    get_job_requirement_snapshot_repository,
)
from app.apps.api.dependencies.transaction import get_transaction
from app.domain.identity import User
from app.domain.imports import ImportDraft, ImportSession, ImportSourceType
from app.domain.opportunity import JobPosting, JobRequirementSnapshot
from app.ports.governance import AuditEventRepository
from app.ports.imports import ImportRepository
from app.ports.opportunity import JobPostingRepository, JobRequirementSnapshotRepository
from app.ports.transaction import Transaction

router = APIRouter(prefix="/imports/jd", tags=["jd-imports"])


class CreateJdImportRequest(BaseModel):
    source_type: Literal["text", "image", "url"]
    jd_text: Annotated[str, Field(min_length=1, max_length=100_000)]
    source_url: str | None = Field(default=None, max_length=2_048)


class EditJdImportDraftRequest(BaseModel):
    base_version: int = Field(ge=1)
    content: JdImportDraftContent


class ConfirmJdImportRequest(BaseModel):
    base_version: int = Field(ge=1)
    content_fingerprint: Annotated[str, StringConstraints(min_length=64, max_length=64)]


class JdImportResponse(BaseModel):
    session_id: UUID
    draft_id: UUID
    source_type: ImportSourceType
    source_url: str | None
    status: str
    version: int
    content_fingerprint: str
    prompt_version: str
    model_version: str
    content: JdImportDraftContent
    failure_code: str | None = None

    @classmethod
    def from_values(cls, session: ImportSession, draft: ImportDraft) -> "JdImportResponse":
        return cls(
            session_id=session.id,
            draft_id=draft.id,
            source_type=session.source_type,
            source_url=session.source_url,
            status=session.status.value,
            version=draft.version,
            content_fingerprint=draft.content_fingerprint,
            prompt_version=draft.prompt_version,
            model_version=draft.model_version,
            content=JdImportDraftContent.model_validate(draft.content),
            failure_code=session.failure_code.value if session.failure_code else None,
        )


class ConfirmJdImportResponse(BaseModel):
    job_posting: dict[str, object]
    requirement_snapshot: dict[str, object]


def _service(
    imports: ImportRepository = Depends(get_import_repository),
    agent: JdImportAgent = Depends(get_jd_import_agent),
    postings: JobPostingRepository = Depends(get_job_posting_repository),
    requirements: JobRequirementSnapshotRepository = Depends(
        get_job_requirement_snapshot_repository
    ),
    audit: AuditEventRepository = Depends(get_audit_event_repository),
    transaction: Transaction = Depends(get_transaction),
) -> JdImportService:
    return JdImportService(imports, agent, postings, requirements, audit, transaction)


@router.post("", response_model=JdImportResponse, status_code=status.HTTP_201_CREATED)
async def create_jd_import(
    payload: CreateJdImportRequest,
    user: User = Depends(get_current_user),
    service: JdImportService = Depends(_service),
) -> JdImportResponse:
    session, draft = await service.create(
        CreateJdImportCommand(
            owner_id=user.id,
            source_type=ImportSourceType(payload.source_type),
            jd_text=payload.jd_text,
            source_url=payload.source_url,
        )
    )
    return JdImportResponse.from_values(session, draft)


@router.get("/{session_id}", response_model=JdImportResponse)
async def get_jd_import(
    session_id: UUID,
    user: User = Depends(get_current_user),
    service: JdImportService = Depends(_service),
) -> JdImportResponse:
    session, draft = await service.get(owner_id=user.id, session_id=session_id)
    return JdImportResponse.from_values(session, draft)


@router.put("/{session_id}/draft", response_model=JdImportResponse)
async def edit_jd_import(
    session_id: UUID,
    payload: EditJdImportDraftRequest,
    user: User = Depends(get_current_user),
    service: JdImportService = Depends(_service),
) -> JdImportResponse:
    session, draft = await service.edit(
        EditJdImportDraftCommand(
            owner_id=user.id,
            session_id=session_id,
            base_version=payload.base_version,
            content=payload.content,
        )
    )
    return JdImportResponse.from_values(session, draft)


@router.post("/{session_id}/confirm", response_model=ConfirmJdImportResponse)
async def confirm_jd_import(
    session_id: UUID,
    payload: ConfirmJdImportRequest,
    user: User = Depends(get_current_user),
    service: JdImportService = Depends(_service),
) -> ConfirmJdImportResponse:
    posting, requirement = await service.confirm(
        ConfirmJdImportCommand(
            owner_id=user.id,
            session_id=session_id,
            base_version=payload.base_version,
            content_fingerprint=payload.content_fingerprint,
        )
    )
    return ConfirmJdImportResponse(
        job_posting=_posting_dict(posting), requirement_snapshot=_requirement_dict(requirement)
    )


def _posting_dict(posting: JobPosting) -> dict[str, object]:
    return {
        "id": posting.id,
        "jd_text": posting.jd_text,
        "job_title": posting.job_title,
        "company_name": posting.company_name,
        "location": posting.location,
        "summary": posting.text_summary,
        "source_type": posting.source_type,
        "source_url": posting.source_url,
        "status": posting.status,
        "version": posting.version,
        "created_at": posting.created_at,
    }


def _requirement_dict(snapshot: JobRequirementSnapshot) -> dict[str, object]:
    return {
        "id": snapshot.id,
        "job_posting_id": snapshot.job_posting_id,
        "job_posting_version": snapshot.job_posting_version,
        "version": snapshot.version,
        "content": snapshot.content,
        "content_hash": snapshot.content_hash,
        "created_at": snapshot.created_at,
        "updated_at": snapshot.updated_at,
    }
