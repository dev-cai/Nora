"""D-021 JD 导入草稿、版本冲突和原子确认测试。"""

from uuid import UUID, uuid4

import pytest
from app.application.imports.jd import (
    ConfirmJdImportCommand,
    CreateJdImportCommand,
    EditJdImportDraftCommand,
    JdImportDraftContent,
    JdImportService,
    normalize_jd_text,
)
from app.domain.base.exceptions import ApplicationError, ErrorCode
from app.domain.governance import AuditEvent
from app.domain.imports import ImportSession, ImportSourceType
from app.domain.opportunity import JobPosting, JobRequirementSnapshot
from app.infrastructure.model import FakeModelAdapter
from app.ports.model import ModelError


def _content(text: str = "负责 Python 后端开发") -> dict[str, object]:
    unknown = {
        "value": None,
        "confirmation_status": "unknown",
        "source_type": "text_range",
        "source_range": None,
    }
    return {
        "jd_text": text,
        "job_title": "后端工程师",
        "company_name": "Nora",
        "location": "上海",
        "requirements": {
            "required_skills": {
                "value": ["Python"],
                "confirmation_status": "unconfirmed",
                "source_type": "text_range",
                "source_range": None,
            },
            "minimum_experience_years": unknown,
            "degree_requirement": unknown,
            "location_requirement": unknown,
            "work_mode": unknown,
        },
    }


class ImportRepository:
    def __init__(self) -> None:
        self.sessions: dict[UUID, ImportSession] = {}
        self.drafts = {}
        self.commits = 0

    async def add_session(self, value):
        self.sessions[value.id] = value
        return value

    async def update_session(self, value):
        self.sessions[value.id] = value
        return value

    async def get_session(self, session_id):
        return self.sessions.get(session_id)

    async def add_draft(self, value):
        self.drafts[value.id] = value
        return value

    async def update_draft(self, value):
        self.drafts[value.id] = value
        return value

    async def get_draft(self, draft_id):
        return self.drafts.get(draft_id)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        return None


class PostingRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, JobPosting] = {}
        self.keys = {}

    async def add_idempotent(self, posting, *, idempotency_key, request_fingerprint):
        self.items[posting.id] = posting
        self.keys[idempotency_key] = (posting, request_fingerprint)
        return posting

    async def get_by_idempotency_key(self, key):
        value = self.keys.get(key)
        if value is None:
            return None
        return type("Stored", (), {"job_posting": value[0], "request_fingerprint": value[1]})()

    async def get_by_id(self, posting_id):
        return self.items.get(posting_id)


class RequirementRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, JobRequirementSnapshot] = {}

    async def add(self, snapshot):
        self.items[snapshot.id] = snapshot
        return snapshot

    async def get_by_id(self, snapshot_id):
        return self.items.get(snapshot_id)

    async def get_latest(self, job_posting_id):
        values = [item for item in self.items.values() if item.job_posting_id == job_posting_id]
        return values[-1] if values else None


class AuditRepository:
    async def add(self, event: AuditEvent):
        return event


class Transaction:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _service(model_responses):
    return JdImportService(
        ImportRepository(),
        FakeModelAdapter(model_responses),
        PostingRepository(),
        RequirementRepository(),
        AuditRepository(),
        Transaction(),
    )


@pytest.mark.asyncio
async def test_normalize_jd_text_deduplicates_ocr_headers():
    assert normalize_jd_text("职位\n职位\n\nPython  后端\r\n") == "职位\nPython 后端"


@pytest.mark.asyncio
async def test_create_edit_and_confirm_jd_import():
    owner_id = uuid4()
    service = _service([_content()])
    session, draft = await service.create(
        CreateJdImportCommand(
            owner_id=owner_id,
            source_type=ImportSourceType.IMAGE,
            jd_text="职位\nPython  后端",
        )
    )
    assert session.status.value == "draft_ready"
    edited_content = JdImportDraftContent.model_validate({**draft.content, "location": "北京"})
    _, edited = await service.edit(
        EditJdImportDraftCommand(
            owner_id=owner_id,
            session_id=session.id,
            base_version=draft.version,
            content=edited_content,
        )
    )
    with pytest.raises(ApplicationError) as conflict:
        await service.confirm(
            ConfirmJdImportCommand(
                owner_id=owner_id,
                session_id=session.id,
                base_version=draft.version,
                content_fingerprint=draft.content_fingerprint,
            )
        )
    assert conflict.value.error_code is ErrorCode.IMPORT_CONFIRMATION_CONFLICT
    posting, requirement = await service.confirm(
        ConfirmJdImportCommand(
            owner_id=owner_id,
            session_id=session.id,
            base_version=edited.version,
            content_fingerprint=edited.content_fingerprint,
        )
    )
    assert posting.location == "北京"
    assert requirement.job_posting_id == posting.id


@pytest.mark.asyncio
async def test_confirm_replay_returns_same_business_objects():
    owner_id = uuid4()
    service = _service([_content()])
    session, draft = await service.create(
        CreateJdImportCommand(owner_id=owner_id, source_type=ImportSourceType.TEXT, jd_text="JD")
    )
    first = await service.confirm(
        ConfirmJdImportCommand(
            owner_id=owner_id,
            session_id=session.id,
            base_version=draft.version,
            content_fingerprint=draft.content_fingerprint,
        )
    )
    replay = await service.confirm(
        ConfirmJdImportCommand(
            owner_id=owner_id,
            session_id=session.id,
            base_version=draft.version,
            content_fingerprint=draft.content_fingerprint,
        )
    )
    assert replay[0].id == first[0].id
    assert replay[1].id == first[1].id


@pytest.mark.asyncio
async def test_model_failure_keeps_a_failed_owner_scoped_session():
    owner_id = uuid4()
    imports = ImportRepository()
    service = JdImportService(
        imports,
        FakeModelAdapter([]),
        PostingRepository(),
        RequirementRepository(),
        AuditRepository(),
        Transaction(),
    )

    with pytest.raises(ModelError):
        await service.create(
            CreateJdImportCommand(
                owner_id=owner_id,
                source_type=ImportSourceType.TEXT,
                jd_text="无法生成草稿的 JD",
            )
        )

    assert len(imports.sessions) == 1
    failed = next(iter(imports.sessions.values()))
    assert failed.owner_id == owner_id
    assert failed.status.value == "failed"
    assert failed.failure_code is ErrorCode.MODEL_PROVIDER_FAILED
