"""当前认证用户的 CandidateProfile 读写 API。"""

from datetime import date, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, StringConstraints, model_validator
from typing_extensions import Annotated, Self

from app.application.career import (
    GetCandidateProfileQuery,
    GetCandidateProfileUseCase,
    PutCandidateProfileCommand,
    PutCandidateProfileUseCase,
)
from app.apps.api.dependencies import get_candidate_profile_repository, get_current_user
from app.domain.career import CandidateProfile, ConfirmationStatus, ProfileSourceType
from app.domain.identity import User
from app.ports.career import CandidateProfileRepository

router = APIRouter(prefix="/profile", tags=["profile"])
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5_000)]


class StringFactInput(BaseModel):
    value: ShortText
    confirmation_status: ConfirmationStatus = ConfirmationStatus.UNCONFIRMED


class OptionalStringFactInput(BaseModel):
    value: ShortText | None = None
    confirmation_status: ConfirmationStatus = ConfirmationStatus.UNCONFIRMED


class BooleanFactInput(BaseModel):
    value: bool
    confirmation_status: ConfirmationStatus = ConfirmationStatus.UNCONFIRMED


class StringListFactInput(BaseModel):
    value: list[ShortText] = Field(default_factory=list, max_length=50)
    confirmation_status: ConfirmationStatus = ConfirmationStatus.UNCONFIRMED


class LongTextListFactInput(BaseModel):
    value: list[LongText] = Field(default_factory=list, max_length=50)
    confirmation_status: ConfirmationStatus = ConfirmationStatus.UNCONFIRMED


class DateFactInput(BaseModel):
    value: date | None = None
    confirmation_status: ConfirmationStatus = ConfirmationStatus.UNCONFIRMED


class YearsFactInput(BaseModel):
    value: float | None = Field(default=None, ge=0, le=100)
    confirmation_status: ConfirmationStatus = ConfirmationStatus.UNCONFIRMED


class BasicInformationInput(BaseModel):
    display_name: StringFactInput
    current_location: StringFactInput


class JobPreferencesInput(BaseModel):
    target_locations: StringListFactInput
    accepts_remote: BooleanFactInput
    target_roles: StringListFactInput


class EducationInput(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    school: StringFactInput
    degree: StringFactInput
    major: StringFactInput
    start_date: DateFactInput
    end_date: DateFactInput

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        if (
            self.start_date.value is not None
            and self.end_date.value is not None
            and self.end_date.value < self.start_date.value
        ):
            raise ValueError("education end_date cannot be earlier than start_date")
        return self


class ExperienceInput(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    company: StringFactInput
    job_title: StringFactInput
    start_date: DateFactInput
    end_date: DateFactInput
    responsibilities: LongTextListFactInput
    achievements: LongTextListFactInput

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        if (
            self.start_date.value is not None
            and self.end_date.value is not None
            and self.end_date.value < self.start_date.value
        ):
            raise ValueError("experience end_date cannot be earlier than start_date")
        return self


class SkillInput(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: StringFactInput
    proficiency: OptionalStringFactInput
    years: YearsFactInput


class CandidateProfileContentInput(BaseModel):
    basic_information: BasicInformationInput
    preferences: JobPreferencesInput
    education: list[EducationInput] = Field(default_factory=list, max_length=50)
    experiences: list[ExperienceInput] = Field(default_factory=list, max_length=50)
    skills: list[SkillInput] = Field(default_factory=list, max_length=100)


class ProfileFactResponse(BaseModel):
    value: str | bool | float | list[str] | None
    confirmation_status: ConfirmationStatus
    source_type: ProfileSourceType
    updated_at: datetime


class BasicInformationResponse(BaseModel):
    display_name: ProfileFactResponse
    current_location: ProfileFactResponse


class JobPreferencesResponse(BaseModel):
    target_locations: ProfileFactResponse
    accepts_remote: ProfileFactResponse
    target_roles: ProfileFactResponse


class EducationResponse(BaseModel):
    id: UUID
    school: ProfileFactResponse
    degree: ProfileFactResponse
    major: ProfileFactResponse
    start_date: ProfileFactResponse
    end_date: ProfileFactResponse


class ExperienceResponse(BaseModel):
    id: UUID
    company: ProfileFactResponse
    job_title: ProfileFactResponse
    start_date: ProfileFactResponse
    end_date: ProfileFactResponse
    responsibilities: ProfileFactResponse
    achievements: ProfileFactResponse


class SkillResponse(BaseModel):
    id: UUID
    name: ProfileFactResponse
    proficiency: ProfileFactResponse
    years: ProfileFactResponse


class CandidateProfileContentResponse(BaseModel):
    basic_information: BasicInformationResponse
    preferences: JobPreferencesResponse
    education: list[EducationResponse]
    experiences: list[ExperienceResponse]
    skills: list[SkillResponse]


class CandidateProfileResponse(BaseModel):
    id: UUID
    owner_id: UUID
    version: int
    content: CandidateProfileContentResponse
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, profile: CandidateProfile) -> "CandidateProfileResponse":
        return cls(
            id=profile.id,
            owner_id=profile.owner_id,
            version=profile.version,
            content=CandidateProfileContentResponse.model_validate(profile.content),
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )


@router.put("", response_model=CandidateProfileResponse)
async def put_candidate_profile(
    payload: CandidateProfileContentInput,
    user: User = Depends(get_current_user),
    repository: CandidateProfileRepository = Depends(get_candidate_profile_repository),
) -> CandidateProfileResponse:
    profile = await PutCandidateProfileUseCase(repository).execute(
        PutCandidateProfileCommand(owner_id=user.id, content=payload.model_dump(mode="json"))
    )
    return CandidateProfileResponse.from_domain(profile)


@router.get("", response_model=CandidateProfileResponse)
async def get_candidate_profile(
    version: Annotated[int | None, Query(ge=1)] = None,
    user: User = Depends(get_current_user),
    repository: CandidateProfileRepository = Depends(get_candidate_profile_repository),
) -> CandidateProfileResponse:
    profile = await GetCandidateProfileUseCase(repository).execute(
        GetCandidateProfileQuery(owner_id=user.id, version=version)
    )
    return CandidateProfileResponse.from_domain(profile)
