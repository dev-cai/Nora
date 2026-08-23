"""文档导入候选状态 Repository 契约。"""

from typing import Any, Protocol
from uuid import UUID

from app.domain.imports import ImportDraft, ImportSession


class JdImportAgentPort(Protocol):
    """Application-facing contract for the fixed JD import graph."""

    async def run(self, jd_text: str) -> Any: ...


class ImportRepository(Protocol):
    async def add_session(self, session: ImportSession) -> ImportSession: ...

    async def update_session(self, session: ImportSession) -> ImportSession: ...

    async def get_session(self, session_id: UUID) -> ImportSession | None: ...

    async def add_draft(self, draft: ImportDraft) -> ImportDraft: ...

    async def update_draft(self, draft: ImportDraft) -> ImportDraft: ...

    async def get_draft(self, draft_id: UUID) -> ImportDraft | None: ...
