"""DecisionCase 输入解析与幂等创建用例。"""

from dataclasses import dataclass
from uuid import UUID

from app.domain.base.exceptions import ApplicationError, InfrastructureError
from app.domain.decision import DecisionCase
from app.ports.career import CandidateProfileRepository, ResumeVersionRepository
from app.ports.decision import DecisionCaseRepository
from app.ports.opportunity import JobPostingRepository, JobRequirementSnapshotRepository


@dataclass(frozen=True, slots=True)
class CreateDecisionCaseCommand:
    """固定一次决策所需的全部用户输入版本。"""

    owner_id: UUID
    job_posting_id: UUID
    job_posting_version: int
    job_requirement_snapshot_id: UUID
    job_requirement_snapshot_version: int
    candidate_profile_id: UUID
    candidate_profile_version: int
    resume_version_id: UUID
    resume_version: int
    rule_set_version: str


@dataclass(frozen=True, slots=True)
class CreateDecisionCaseResult:
    """DecisionCase 创建结果及幂等重放标记。"""

    decision_case: DecisionCase
    replayed: bool


@dataclass(frozen=True, slots=True)
class GetDecisionCaseQuery:
    """读取当前用户的一条 DecisionCase。"""

    owner_id: UUID
    case_id: UUID


class CreateDecisionCaseUseCase:
    """验证同一用户的精确输入版本并幂等创建 DecisionCase。"""

    def __init__(
        self,
        repository: DecisionCaseRepository,
        posting_repository: JobPostingRepository,
        requirement_repository: JobRequirementSnapshotRepository,
        profile_repository: CandidateProfileRepository,
        resume_repository: ResumeVersionRepository,
    ) -> None:
        self.repository = repository
        self.posting_repository = posting_repository
        self.requirement_repository = requirement_repository
        self.profile_repository = profile_repository
        self.resume_repository = resume_repository

    async def execute(self, command: CreateDecisionCaseCommand) -> CreateDecisionCaseResult:
        candidate = DecisionCase.create(
            owner_id=command.owner_id,
            job_posting_id=command.job_posting_id,
            job_posting_version=command.job_posting_version,
            job_requirement_snapshot_id=command.job_requirement_snapshot_id,
            job_requirement_snapshot_version=command.job_requirement_snapshot_version,
            candidate_profile_id=command.candidate_profile_id,
            candidate_profile_version=command.candidate_profile_version,
            resume_version_id=command.resume_version_id,
            resume_version=command.resume_version,
            rule_set_version=command.rule_set_version,
        )
        existing = await self.repository.get_by_input_fingerprint(candidate.input_fingerprint)
        if existing is not None:
            if existing.owner_id != command.owner_id:
                raise ApplicationError("Decision input not found", error_code="entity_not_found")
            return CreateDecisionCaseResult(decision_case=existing, replayed=True)

        posting = await self.posting_repository.get_by_id(command.job_posting_id)
        requirement = await self.requirement_repository.get_version(
            command.job_posting_id, command.job_requirement_snapshot_version
        )
        profile = await self.profile_repository.get_version(command.candidate_profile_version)
        resume = await self.resume_repository.get_by_id(command.resume_version_id)

        valid_inputs = (
            posting is not None
            and posting.owner_id == command.owner_id
            and posting.version == command.job_posting_version
            and requirement is not None
            and requirement.id == command.job_requirement_snapshot_id
            and requirement.owner_id == command.owner_id
            and requirement.version == command.job_requirement_snapshot_version
            and requirement.job_posting_id == command.job_posting_id
            and requirement.job_posting_version == command.job_posting_version
            and profile is not None
            and profile.id == command.candidate_profile_id
            and profile.owner_id == command.owner_id
            and profile.version == command.candidate_profile_version
            and resume is not None
            and resume.owner_id == command.owner_id
            and resume.version == command.resume_version
            and resume.candidate_profile_id == command.candidate_profile_id
            and resume.profile_version == command.candidate_profile_version
        )
        if not valid_inputs:
            raise ApplicationError("Decision input not found", error_code="entity_not_found")

        try:
            stored = await self.repository.add(candidate)
            await self.repository.commit()
        except InfrastructureError as exc:
            if exc.error_code != "decision_case_conflict":
                raise
            replay = await self.repository.get_by_input_fingerprint(candidate.input_fingerprint)
            if replay is None:
                raise
            return CreateDecisionCaseResult(decision_case=replay, replayed=True)
        return CreateDecisionCaseResult(decision_case=stored, replayed=False)


class GetDecisionCaseUseCase:
    """按用户范围读取 DecisionCase，不泄露跨用户存在性。"""

    def __init__(self, repository: DecisionCaseRepository) -> None:
        self.repository = repository

    async def execute(self, query: GetDecisionCaseQuery) -> DecisionCase:
        decision_case = await self.repository.get_by_id(query.case_id)
        if decision_case is None or decision_case.owner_id != query.owner_id:
            raise ApplicationError("Decision case not found", error_code="entity_not_found")
        return decision_case
