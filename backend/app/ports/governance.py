"""Governance 应用层依赖的审计 Repository 契约。"""

from typing import Protocol

from app.domain.governance import AuditEvent


class AuditEventRepository(Protocol):
    """只暴露追加能力的审计事件端口。"""

    async def add(self, event: AuditEvent) -> AuditEvent: ...
