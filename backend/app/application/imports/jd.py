"""JD Import Context：固定解析、草稿编辑和一次整体确认。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.base.exceptions import ApplicationError, DomainError, ErrorCode
from app.domain.governance import AuditAction, AuditEvent
from app.domain.imports import (
    ImportDraft,
    ImportSession,
    ImportSessionStatus,
    ImportSourceType,
)
from app.domain.opportunity import JobPosting, JobRequirementSnapshot, JobSourceType
from app.ports.governance import AuditEventRepository
from app.ports.imports import ImportRepository, JdImportAgentPort
from app.ports.model import ModelError
from app.ports.opportunity import JobPostingRepository, JobRequirementSnapshotRepository
from app.ports.transaction import Transaction

JD_IMPORT_PROMPT_VERSION = "jd-import-v1"
JD_IMPORT_MODEL_VERSION = "deepseek-v4-flash"
_TEXT_RE = re.compile(r"[ \t]+")


class JdRequirementFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Any = None
    confirmation_status: Literal["unknown", "unconfirmed", "confirmed"] = "unknown"
    source_type: Literal["manual", "text_range", "ocr_preview"] = "text_range"
    source_range: str | None = Field(default=None, max_length=64)


class JdRequirementDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_skills: JdRequirementFact
    minimum_experience_years: JdRequirementFact
    degree_requirement: JdRequirementFact
    location_requirement: JdRequirementFact
    work_mode: JdRequirementFact


class JdImportDraftContent(BaseModel):
    """用户可编辑的 JD 候选字段；不是业务事实。"""

    model_config = ConfigDict(extra="forbid")

    jd_text: Annotated[str, Field(min_length=1, max_length=100_000)]
    job_title: str | None = Field(default=None, max_length=200)
    company_name: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    requirements: JdRequirementDraft


@dataclass(frozen=True, slots=True)
class CreateJdImportCommand:
    owner_id: UUID
    source_type: ImportSourceType
    jd_text: str
    source_url: str | None = None


@dataclass(frozen=True, slots=True)
class EditJdImportDraftCommand:
    owner_id: UUID
    session_id: UUID
    base_version: int
    content: JdImportDraftContent


@dataclass(frozen=True, slots=True)
class ConfirmJdImportCommand:
    owner_id: UUID
    session_id: UUID
    base_version: int
    content_fingerprint: str


class JdImportService:
    """固定的 JD 导入 Graph：清洗 → 结构化候选 → 校验 → 等待确认 → 原子写入。"""

    def __init__(
        self,
        import_repository: ImportRepository,
        agent: JdImportAgentPort,
        posting_repository: JobPostingRepository,
        requirement_repository: JobRequirementSnapshotRepository,
        audit_repository: AuditEventRepository,
        transaction: Transaction,
    ) -> None:
        self.import_repository = import_repository
        self.agent = agent
        self.posting_repository = posting_repository
        self.requirement_repository = requirement_repository
        self.audit_repository = audit_repository
        self.transaction = transaction

    async def create(self, command: CreateJdImportCommand) -> tuple[ImportSession, ImportDraft]:
        session = ImportSession.create(
            owner_id=command.owner_id,
            source_type=command.source_type,
            source_url=command.source_url,
        )
        await self.import_repository.add_session(session)
        await self.transaction.commit()
        try:
            content = validate_jd_content(await self.agent.run(command.jd_text))
            draft = ImportDraft.create(
                session_id=session.id,
                owner_id=command.owner_id,
                content=content.model_dump(mode="json"),
                prompt_version=JD_IMPORT_PROMPT_VERSION,
                model_version=JD_IMPORT_MODEL_VERSION,
            )
            await self.import_repository.add_draft(draft)
            session = session.with_draft(draft.id)
            await self.import_repository.update_session(session)
            await self.transaction.commit()
            return session, draft
        except (ModelError, DomainError) as exc:
            await self.transaction.rollback()
            failed = session.failed(exc.error_code)
            await self.import_repository.update_session(failed)
            await self.transaction.commit()
            raise
        except Exception:
            await self.transaction.rollback()
            failed = session.failed(ErrorCode.IMPORT_PERSISTENCE_FAILED)
            await self.import_repository.update_session(failed)
            await self.transaction.commit()
            raise

    async def get(self, *, owner_id: UUID, session_id: UUID) -> tuple[ImportSession, ImportDraft]:
        session = await self._session(owner_id, session_id)
        if session.current_draft_id is None:
            raise ApplicationError(
                "Import draft is not ready", error_code=ErrorCode.IMPORT_NOT_READY
            )
        draft = await self.import_repository.get_draft(session.current_draft_id)
        if draft is None:
            raise ApplicationError(
                "Import draft is not available", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        return session, draft

    async def edit(self, command: EditJdImportDraftCommand) -> tuple[ImportSession, ImportDraft]:
        session, draft = await self.get(owner_id=command.owner_id, session_id=command.session_id)
        if session.status is not ImportSessionStatus.DRAFT_READY:
            raise ApplicationError(
                "Import draft is not editable", error_code=ErrorCode.IMPORT_NOT_READY
            )
        edited_content = validate_jd_content(command.content)
        edited = draft.edit(
            base_version=command.base_version,
            content=edited_content.model_dump(mode="json"),
        )
        await self.import_repository.update_draft(edited)
        await self.transaction.commit()
        return session, edited

    async def confirm(
        self, command: ConfirmJdImportCommand
    ) -> tuple[JobPosting, JobRequirementSnapshot]:
        session, draft = await self.get(owner_id=command.owner_id, session_id=command.session_id)
        if session.status is ImportSessionStatus.CONFIRMED:
            if (
                command.base_version != draft.version
                or command.content_fingerprint != draft.content_fingerprint
                or session.confirmed_job_posting_id is None
                or session.confirmed_requirement_snapshot_id is None
            ):
                raise ApplicationError(
                    "Import confirmation conflicts with the confirmed draft",
                    error_code=ErrorCode.IMPORT_CONFIRMATION_CONFLICT,
                )
            posting = await self.posting_repository.get_by_id(session.confirmed_job_posting_id)
            requirement = await self.requirement_repository.get_by_id(
                session.confirmed_requirement_snapshot_id
            )
            if posting is None or requirement is None:
                raise ApplicationError(
                    "Confirmed import result is unavailable", error_code=ErrorCode.ENTITY_NOT_FOUND
                )
            return posting, requirement
        if session.status is not ImportSessionStatus.DRAFT_READY:
            raise ApplicationError(
                "Import draft is not ready for confirmation", error_code=ErrorCode.IMPORT_NOT_READY
            )
        if (
            command.base_version != draft.version
            or command.content_fingerprint != draft.content_fingerprint
        ):
            raise ApplicationError(
                "Import draft has changed; refresh before confirming",
                error_code=ErrorCode.IMPORT_CONFIRMATION_CONFLICT,
            )

        content = JdImportDraftContent.model_validate(draft.content)
        posting = JobPosting.create(
            owner_id=command.owner_id,
            jd_text=content.jd_text,
            job_title=content.job_title,
            company_name=content.company_name,
            location=content.location,
            source_type=JobSourceType.URL
            if session.source_type is ImportSourceType.URL
            else JobSourceType.MANUAL,
            source_url=session.source_url,
        )
        requirements_content = content.requirements.model_dump(mode="json")
        requirement = JobRequirementSnapshot.create(
            owner_id=command.owner_id,
            job_posting_id=posting.id,
            job_posting_version=posting.version,
            content=requirements_content,
        )
        key = f"jd-import:{session.id}:{draft.content_fingerprint}"
        existing = await self.posting_repository.get_by_idempotency_key(key)
        if existing is not None:
            if existing.request_fingerprint != draft.content_fingerprint:
                raise ApplicationError(
                    "Import confirmation idempotency conflict",
                    error_code=ErrorCode.IMPORT_CONFIRMATION_CONFLICT,
                )
            existing_requirement = await self.requirement_repository.get_latest(
                existing.job_posting.id
            )
            if existing_requirement is None:
                raise ApplicationError(
                    "Confirmed import requirement is unavailable",
                    error_code=ErrorCode.IMPORT_PERSISTENCE_FAILED,
                )
            await self.import_repository.update_session(
                session.confirmed(
                    job_posting_id=existing.job_posting.id,
                    requirement_snapshot_id=existing_requirement.id,
                )
            )
            await self.transaction.commit()
            return existing.job_posting, existing_requirement
        try:
            stored_posting = await self.posting_repository.add_idempotent(
                posting,
                idempotency_key=key,
                request_fingerprint=draft.content_fingerprint,
            )
            stored_requirement = await self.requirement_repository.add(requirement)
            await self.audit_repository.add(
                AuditEvent.create(
                    actor_id=command.owner_id,
                    action=AuditAction.CREATE,
                    target_type="jd_import",
                    target_id=session.id,
                    target_version=draft.version,
                    after_summary=json.dumps(
                        {
                            "job_posting_id": str(stored_posting.id),
                            "requirement_version": stored_requirement.version,
                        }
                    ),
                    idempotency_key=key,
                )
            )
            await self.import_repository.update_session(
                session.confirmed(
                    job_posting_id=stored_posting.id,
                    requirement_snapshot_id=stored_requirement.id,
                )
            )
            await self.transaction.commit()
        except Exception:
            await self.transaction.rollback()
            raise
        return stored_posting, stored_requirement

    async def _session(self, owner_id: UUID, session_id: UUID) -> ImportSession:
        session = await self.import_repository.get_session(session_id)
        if session is None or session.owner_id != owner_id:
            raise ApplicationError(
                "Import session not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        return session


def normalize_jd_text(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainError("JD text is empty", error_code=ErrorCode.INVALID_DRAFT_TEXT)
    lines: list[str] = []
    seen: set[str] = set()
    for raw_line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = _TEXT_RE.sub(" ", raw_line).strip()
        if not line or line in seen:
            continue
        lines.append(line)
        seen.add(line)
    normalized = "\n".join(lines)
    if len(normalized) > 100_000:
        raise DomainError("JD text is too long", error_code=ErrorCode.JD_TEXT_TOO_LONG)
    return normalized


def validate_jd_content(content: JdImportDraftContent) -> JdImportDraftContent:
    # Reuse the domain's strict requirement invariants before a draft is persisted.
    JobRequirementSnapshot.create(
        owner_id=UUID(int=0),
        job_posting_id=UUID(int=0),
        job_posting_version=1,
        content=content.requirements.model_dump(mode="json"),
    )
    return content


__all__ = (
    "ConfirmJdImportCommand",
    "CreateJdImportCommand",
    "EditJdImportDraftCommand",
    "JD_IMPORT_MODEL_VERSION",
    "JD_IMPORT_PROMPT_VERSION",
    "JdImportDraftContent",
    "JdImportService",
    "normalize_jd_text",
    "validate_jd_content",
)
