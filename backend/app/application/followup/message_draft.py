"""Generate and revise deterministic MessageDraft records."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.domain.base.exceptions import ApplicationError, ErrorCode, InfrastructureError
from app.domain.decision import CompanyAssessmentStatus
from app.domain.followup import (
    ApplicationDecisionStatus,
    MessageDraft,
    MessageDraftSource,
    MessageDraftStyle,
    edit_request_fingerprint,
    normalize_message_draft_idempotency_key,
)
from app.domain.opportunity import CompanyFieldStatus
from app.ports.career import ResumeVersionRepository
from app.ports.decision import CompanyAssessmentRepository, DecisionCaseRepository
from app.ports.followup import (
    ApplicationDecisionRepository,
    MessageDraftRepository,
    ResumeVariantRepository,
)
from app.ports.opportunity import CompanySnapshotRepository, JobPostingRepository


@dataclass(frozen=True, slots=True)
class GenerateMessageDraftCommand:
    owner_id: UUID
    resume_variant_id: UUID
    style: MessageDraftStyle
    user_note: str | None
    referral_context: str | None
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class EditMessageDraftCommand:
    owner_id: UUID
    draft_id: UUID
    base_version: int
    text: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class MessageDraftMutationResult:
    draft: MessageDraft
    replayed: bool


@dataclass(frozen=True, slots=True)
class ListMessageDraftsQuery:
    owner_id: UUID
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True, slots=True)
class ListMessageDraftsResult:
    items: tuple[MessageDraft, ...]
    page: int
    page_size: int
    total: int


class MessageDraftUseCases:
    def __init__(
        self,
        drafts: MessageDraftRepository,
        variants: ResumeVariantRepository,
        decisions: ApplicationDecisionRepository,
        cases: DecisionCaseRepository,
        resumes: ResumeVersionRepository,
        jobs: JobPostingRepository,
        assessments: CompanyAssessmentRepository,
        companies: CompanySnapshotRepository,
    ) -> None:
        self.drafts = drafts
        self.variants = variants
        self.decisions = decisions
        self.cases = cases
        self.resumes = resumes
        self.jobs = jobs
        self.assessments = assessments
        self.companies = companies

    async def generate(self, command: GenerateMessageDraftCommand) -> MessageDraftMutationResult:
        variant = await self.variants.get_by_id(command.resume_variant_id)
        if variant is None or variant.owner_id != command.owner_id:
            raise ApplicationError(
                "Resume variant not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        decision = await self.decisions.get_by_id(variant.application_decision_id)
        decision_case = await self.cases.get_by_id(variant.decision_case_id)
        resume = await self.resumes.get_by_identity(
            variant.resume_version_id, variant.resume_version
        )
        job = await self.jobs.get_by_id(variant.job_posting_id)
        if (
            decision is None
            or decision.owner_id != command.owner_id
            or decision.status is not ApplicationDecisionStatus.APPLY
            or decision_case is None
            or decision_case.owner_id != command.owner_id
            or resume is None
            or resume.owner_id != command.owner_id
            or job is None
            or job.owner_id != command.owner_id
            or job.version != variant.job_posting_version
        ):
            raise ApplicationError(
                "Message draft input not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        company_snapshot_id: UUID | None = None
        company_snapshot_version: int | None = None
        company_snapshot_hash: str | None = None
        company_freshness: str | None = None
        company_industry: str | None = None
        assessment = await self.assessments.get_for_report(decision.report_id)
        if assessment is not None:
            snapshot = await self.companies.get_by_identity(
                assessment.company_snapshot_id, assessment.company_snapshot_version
            )
            if snapshot is None or snapshot.owner_id != command.owner_id:
                raise ApplicationError(
                    "Message draft company input is unavailable",
                    error_code=ErrorCode.MESSAGE_DRAFT_INPUT_UNAVAILABLE,
                )
            company_snapshot_id = snapshot.id
            company_snapshot_version = snapshot.version
            company_snapshot_hash = snapshot.content_sha256
            company_freshness = snapshot.freshness.value
            company_industry = (
                snapshot.industry
                if assessment.status is CompanyAssessmentStatus.AVAILABLE
                and snapshot.industry_status is CompanyFieldStatus.CONFIRMED
                else None
            )
        source = MessageDraftSource(
            application_decision_id=decision.id,
            report_id=decision.report_id,
            report_version=decision.report_version,
            decision_case_id=decision_case.id,
            resume_variant_id=variant.id,
            resume_variant_version=variant.version,
            variant_content_fingerprint=variant.content_fingerprint,
            candidate_profile_id=resume.candidate_profile_id,
            candidate_profile_version=resume.profile_version,
            resume_version_id=resume.id,
            resume_version=resume.version,
            job_posting_id=job.id,
            job_posting_version=job.version,
            display_name=_display_name(resume.content),
            company_name=job.company_name,
            job_title=job.job_title,
            skills=_skills(resume.content),
            company_snapshot_id=company_snapshot_id,
            company_snapshot_version=company_snapshot_version,
            company_snapshot_hash=company_snapshot_hash,
            company_freshness=company_freshness,
            company_industry=company_industry,
        )
        candidate = MessageDraft.generate(
            owner_id=command.owner_id,
            source=source,
            style=command.style,
            user_note=command.user_note,
            referral_context=command.referral_context,
            idempotency_key=command.idempotency_key,
        )
        existing_key = await self.drafts.get_by_idempotency_key(candidate.idempotency_key)
        if existing_key is not None:
            return _replay(existing_key, candidate.request_fingerprint)
        existing_generation = await self.drafts.get_by_generation_identity(
            candidate.generation_identity
        )
        if existing_generation is not None:
            return MessageDraftMutationResult(draft=existing_generation, replayed=True)
        return await self._store(candidate)

    async def edit(self, command: EditMessageDraftCommand) -> MessageDraftMutationResult:
        request_fingerprint = edit_request_fingerprint(
            command.draft_id, command.base_version, command.text
        )
        idempotency_key = normalize_message_draft_idempotency_key(command.idempotency_key)
        existing_key = await self.drafts.get_by_idempotency_key(idempotency_key)
        if existing_key is not None:
            if existing_key.owner_id != command.owner_id:
                raise ApplicationError(
                    "Message draft not found", error_code=ErrorCode.ENTITY_NOT_FOUND
                )
            return _replay(existing_key, request_fingerprint)
        current = await self.get(command.owner_id, command.draft_id)
        if current.version != command.base_version:
            raise ApplicationError(
                "Message draft version conflict",
                error_code=ErrorCode.MESSAGE_DRAFT_VERSION_CONFLICT,
            )
        return await self._store(current.edit(text=command.text, idempotency_key=idempotency_key))

    async def _store(self, candidate: MessageDraft) -> MessageDraftMutationResult:
        try:
            stored = await self.drafts.add(candidate)
            await self.drafts.commit()
            return MessageDraftMutationResult(draft=stored, replayed=False)
        except InfrastructureError as exc:
            if exc.error_code != "message_draft_conflict":
                raise
            existing = await self.drafts.get_by_idempotency_key(candidate.idempotency_key)
            if existing is None and candidate.version == 1:
                existing = await self.drafts.get_by_generation_identity(
                    candidate.generation_identity
                )
            if existing is None:
                raise ApplicationError(
                    "Message draft version conflict",
                    error_code=ErrorCode.MESSAGE_DRAFT_VERSION_CONFLICT,
                ) from exc
            return _replay(existing, candidate.request_fingerprint)

    async def get(self, owner_id: UUID, draft_id: UUID) -> MessageDraft:
        value = await self.drafts.get_latest(draft_id)
        if value is None or value.owner_id != owner_id:
            raise ApplicationError("Message draft not found", error_code=ErrorCode.ENTITY_NOT_FOUND)
        return value

    async def get_version(self, owner_id: UUID, draft_id: UUID, version: int) -> MessageDraft:
        value = await self.drafts.get_version(draft_id, version)
        if value is None or value.owner_id != owner_id:
            raise ApplicationError("Message draft not found", error_code=ErrorCode.ENTITY_NOT_FOUND)
        return value

    async def get_latest_for_variant(self, owner_id: UUID, variant_id: UUID) -> MessageDraft | None:
        variant = await self.variants.get_by_id(variant_id)
        if variant is None or variant.owner_id != owner_id:
            raise ApplicationError(
                "Resume variant not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        return await self.drafts.get_latest_by_variant(variant_id)

    async def list(self, query: ListMessageDraftsQuery) -> ListMessageDraftsResult:
        if query.page < 1 or not 1 <= query.page_size <= 100:
            raise ApplicationError("Pagination is invalid", error_code=ErrorCode.INVALID_PAGINATION)
        return ListMessageDraftsResult(
            items=tuple(
                await self.drafts.list(
                    offset=(query.page - 1) * query.page_size,
                    limit=query.page_size,
                )
            ),
            page=query.page,
            page_size=query.page_size,
            total=await self.drafts.count(),
        )

    async def list_versions(self, owner_id: UUID, draft_id: UUID) -> tuple[MessageDraft, ...]:
        await self.get(owner_id, draft_id)
        return tuple(await self.drafts.list_versions(draft_id))


def _replay(existing: MessageDraft, request_fingerprint: str) -> MessageDraftMutationResult:
    if existing.request_fingerprint != request_fingerprint:
        raise ApplicationError(
            "Idempotency key was already used with different content",
            error_code=ErrorCode.IDEMPOTENCY_CONFLICT,
        )
    return MessageDraftMutationResult(draft=existing, replayed=True)


def _display_name(content: dict[str, Any]) -> str:
    basic = content.get("basic_information")
    value = basic.get("display_name") if isinstance(basic, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise ApplicationError(
            "Confirmed display name is unavailable",
            error_code=ErrorCode.MESSAGE_DRAFT_INPUT_UNAVAILABLE,
        )
    return value


def _skills(content: dict[str, Any]) -> tuple[str, ...]:
    values = content.get("skills")
    if not isinstance(values, list):
        return ()
    result: list[str] = []
    for item in values:
        value = item.get("name") if isinstance(item, dict) else None
        if isinstance(value, str) and value.strip() and value.strip() not in result:
            result.append(value.strip())
    return tuple(result[:20])
