"""Application use cases for minimal interview notification records."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.base.exceptions import ApplicationError, ErrorCode, InfrastructureError
from app.domain.followup import (
    ApplicationRecordStatus,
    InterviewCase,
    InterviewCaseStatus,
    InterviewMode,
    interview_case_request_fingerprint,
    normalize_interview_idempotency_key,
)
from app.domain.governance import AuditAction, AuditEvent
from app.ports.followup import ApplicationRecordRepository, InterviewCaseRepository
from app.ports.governance import AuditEventRepository
from app.ports.transaction import Transaction


@dataclass(frozen=True, slots=True)
class CreateInterviewCaseCommand:
    owner_id: UUID
    actor_id: UUID
    application_record_id: UUID
    starts_at: datetime
    timezone: str
    mode: InterviewMode
    location: str | None
    meeting_url: str | None
    round_number: int
    note: str | None
    status: InterviewCaseStatus
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class UpdateInterviewCaseCommand:
    owner_id: UUID
    actor_id: UUID
    interview_case_id: UUID
    base_version: int
    starts_at: datetime
    timezone: str
    mode: InterviewMode
    location: str | None
    meeting_url: str | None
    round_number: int
    note: str | None
    status: InterviewCaseStatus
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class ListInterviewCasesQuery:
    owner_id: UUID
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True, slots=True)
class InterviewCaseMutationResult:
    interview: InterviewCase
    replayed: bool


@dataclass(frozen=True, slots=True)
class InterviewCaseListResult:
    items: list[InterviewCase]
    page: int
    page_size: int
    total: int


class InterviewCaseUseCases:
    def __init__(
        self,
        interviews: InterviewCaseRepository,
        applications: ApplicationRecordRepository,
        audits: AuditEventRepository,
        transaction: Transaction,
    ) -> None:
        self.interviews = interviews
        self.applications = applications
        self.audits = audits
        self.transaction = transaction

    async def create(self, command: CreateInterviewCaseCommand) -> InterviewCaseMutationResult:
        candidate = InterviewCase.create(
            owner_id=command.owner_id,
            actor_id=command.actor_id,
            application_record_id=command.application_record_id,
            starts_at=command.starts_at,
            timezone_name=command.timezone,
            mode=command.mode,
            location=command.location,
            meeting_url=command.meeting_url,
            round_number=command.round_number,
            note=command.note,
            status=command.status,
            idempotency_key=command.idempotency_key,
        )
        existing = await self.interviews.get_by_idempotency_key(candidate.idempotency_key)
        if existing is not None:
            return _resolve_replay(existing, candidate.request_fingerprint)
        application = await self.applications.get_by_id(command.application_record_id)
        if application is None or application.owner_id != command.owner_id:
            raise ApplicationError(
                "Application record not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        if application.status is not ApplicationRecordStatus.INTERVIEWING:
            raise ApplicationError(
                "Application record must be confirmed as interviewing",
                error_code=ErrorCode.INTERVIEW_CASE_APPLICATION_CONFLICT,
            )
        return await self._store(candidate, before=None)

    async def update(self, command: UpdateInterviewCaseCommand) -> InterviewCaseMutationResult:
        key = normalize_interview_idempotency_key(command.idempotency_key)
        current = await self._get(command.owner_id, command.interview_case_id)
        normalized = _normalized_candidate(command)
        fingerprint = interview_case_request_fingerprint(
            application_record_id=current.application_record_id,
            base_version=command.base_version,
            starts_at=normalized.starts_at,
            timezone=normalized.timezone,
            mode=normalized.mode,
            location=normalized.location,
            meeting_url=normalized.meeting_url,
            round_number=normalized.round_number,
            note=normalized.note,
            status=normalized.status,
        )
        existing = await self.interviews.get_by_idempotency_key(key)
        if existing is not None:
            return _resolve_replay(existing, fingerprint)
        if command.base_version != current.version:
            raise ApplicationError(
                "Interview case version changed",
                error_code=ErrorCode.INTERVIEW_CASE_VERSION_CONFLICT,
            )
        updated = current.update(
            actor_id=command.actor_id,
            starts_at=command.starts_at,
            timezone_name=command.timezone,
            mode=command.mode,
            location=command.location,
            meeting_url=command.meeting_url,
            round_number=command.round_number,
            note=command.note,
            status=command.status,
            idempotency_key=key,
        )
        return await self._store(updated, before=current)

    async def get(self, owner_id: UUID, interview_id: UUID) -> InterviewCase:
        return await self._get(owner_id, interview_id)

    async def get_version(self, owner_id: UUID, interview_id: UUID, version: int) -> InterviewCase:
        interview = await self.interviews.get_version(interview_id, version)
        if interview is None or interview.owner_id != owner_id:
            raise ApplicationError("Interview not found", error_code=ErrorCode.ENTITY_NOT_FOUND)
        return interview

    async def list_cases(self, query: ListInterviewCasesQuery) -> InterviewCaseListResult:
        if query.page < 1 or not 1 <= query.page_size <= 100:
            raise ApplicationError("Pagination is invalid", error_code=ErrorCode.INVALID_PAGINATION)
        return InterviewCaseListResult(
            items=await self.interviews.list_latest(
                offset=(query.page - 1) * query.page_size,
                limit=query.page_size,
            ),
            page=query.page,
            page_size=query.page_size,
            total=await self.interviews.count(),
        )

    async def list_versions(self, owner_id: UUID, interview_id: UUID) -> list[InterviewCase]:
        await self._get(owner_id, interview_id)
        return await self.interviews.list_versions(interview_id)

    async def _get(self, owner_id: UUID, interview_id: UUID) -> InterviewCase:
        interview = await self.interviews.get_latest(interview_id)
        if interview is None or interview.owner_id != owner_id:
            raise ApplicationError("Interview not found", error_code=ErrorCode.ENTITY_NOT_FOUND)
        return interview

    async def _store(
        self,
        interview: InterviewCase,
        *,
        before: InterviewCase | None,
    ) -> InterviewCaseMutationResult:
        try:
            stored = await self.interviews.add(interview)
            await self.audits.add(
                AuditEvent.create(
                    actor_id=interview.actor_id,
                    action=AuditAction.CREATE if before is None else AuditAction.UPDATE,
                    target_type="interview_case",
                    target_id=stored.id,
                    target_version=stored.version,
                    before_summary=None if before is None else _audit_summary(before),
                    after_summary=_audit_summary(stored),
                    idempotency_key=stored.idempotency_key,
                )
            )
            await self.transaction.commit()
        except InfrastructureError as exc:
            await self.transaction.rollback()
            if exc.error_code not in {
                ErrorCode.INTERVIEW_CASE_KEY_TAKEN,
                ErrorCode.INTERVIEW_CASE_VERSION_CONFLICT,
            }:
                raise
            winner = await self.interviews.get_by_idempotency_key(interview.idempotency_key)
            if winner is not None:
                return _resolve_replay(winner, interview.request_fingerprint)
            if exc.error_code is ErrorCode.INTERVIEW_CASE_VERSION_CONFLICT:
                raise ApplicationError(
                    "Interview case version changed",
                    error_code=ErrorCode.INTERVIEW_CASE_VERSION_CONFLICT,
                ) from exc
            raise InfrastructureError(
                "Could not recover interview case",
                error_code=ErrorCode.INTERVIEW_CASE_PERSISTENCE_FAILED,
            ) from exc
        except Exception:
            await self.transaction.rollback()
            raise
        return InterviewCaseMutationResult(interview=stored, replayed=False)


def _normalized_candidate(command: UpdateInterviewCaseCommand) -> InterviewCase:
    return InterviewCase.create(
        owner_id=command.owner_id,
        actor_id=command.actor_id,
        application_record_id=command.interview_case_id,
        starts_at=command.starts_at,
        timezone_name=command.timezone,
        mode=command.mode,
        location=command.location,
        meeting_url=command.meeting_url,
        round_number=command.round_number,
        note=command.note,
        status=command.status,
        idempotency_key=command.idempotency_key,
    )


def _resolve_replay(existing: InterviewCase, fingerprint: str) -> InterviewCaseMutationResult:
    if not existing.has_same_request(fingerprint):
        raise ApplicationError(
            "Idempotency key belongs to a different interview request",
            error_code=ErrorCode.INTERVIEW_CASE_KEY_TAKEN,
        )
    return InterviewCaseMutationResult(interview=existing, replayed=True)


def _audit_summary(interview: InterviewCase) -> str:
    return (
        f"application={interview.application_record_id};version={interview.version};"
        f"status={interview.status.value};mode={interview.mode.value};"
        f"starts_at={interview.starts_at.isoformat()};timezone={interview.timezone};"
        f"round={interview.round_number}"
    )
