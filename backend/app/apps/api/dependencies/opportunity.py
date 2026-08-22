"""Opportunity API composition dependencies."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.api.dependencies.common import get_current_user, get_session, get_settings
from app.domain.identity import User
from app.infrastructure.config import Settings
from app.infrastructure.database import (
    SqlAlchemyCompanySnapshotRepository,
    SqlAlchemyImportRepository,
    SqlAlchemyJobPostingRepository,
    SqlAlchemyJobRequirementSnapshotRepository,
)
from app.infrastructure.jd_fetch import JdFetchAdapter
from app.infrastructure.jd_ocr import BaiduOcrEngine, JdOcrAdapter
from app.ports.imports import ImportRepository
from app.ports.jd_input import JdInputPort
from app.ports.opportunity import (
    CompanySnapshotRepository,
    JobPostingRepository,
    JobRequirementSnapshotRepository,
)


def get_job_posting_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> JobPostingRepository:
    return SqlAlchemyJobPostingRepository(session, user.id)


def get_import_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ImportRepository:
    return SqlAlchemyImportRepository(session, user.id)


def get_job_requirement_snapshot_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> JobRequirementSnapshotRepository:
    return SqlAlchemyJobRequirementSnapshotRepository(session, user.id)


def get_company_snapshot_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> CompanySnapshotRepository:
    return SqlAlchemyCompanySnapshotRepository(session, user.id)


def get_jd_input_adapter() -> JdInputPort:
    return JdFetchAdapter()


def get_jd_ocr_adapter(settings: Settings = Depends(get_settings)) -> JdInputPort:
    return JdOcrAdapter(
        engine=BaiduOcrEngine(
            api_key=settings.baidu_ocr_api_key,
            secret_key=settings.baidu_ocr_secret_key,
            endpoint=settings.baidu_ocr_endpoint,
        )
    )
