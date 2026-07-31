"""Governance 审计事件 ORM 模型和只追加 Repository。"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from nora.domain.governance import AuditAction, AuditEvent
from nora.infrastructure.database.base import Base


class AuditEventRecord(Base):
    """由数据库迁移保护为不可更新、不可删除的审计记录。"""

    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "action IN ('create', 'read', 'update', 'delete')",
            name="ck_audit_events_action",
        ),
        Index("ix_audit_events_target", "target_type", "target_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    target_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    before_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)


class SqlAlchemyAuditEventRepository:
    """仅允许向当前事务追加审计事件。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, event: AuditEvent) -> AuditEvent:
        self.session.add(
            AuditEventRecord(
                id=event.id,
                actor_id=event.actor_id,
                action=event.action.value,
                target_type=event.target_type,
                target_id=event.target_id,
                before_summary=event.before_summary,
                after_summary=event.after_summary,
                occurred_at=event.occurred_at,
                idempotency_key=event.idempotency_key,
            )
        )
        return event

    @staticmethod
    def to_domain(record: AuditEventRecord) -> AuditEvent:
        """将持久化记录恢复为不可变领域事件。"""

        return AuditEvent(
            id=record.id,
            actor_id=record.actor_id,
            action=AuditAction(record.action),
            target_type=record.target_type,
            target_id=record.target_id,
            before_summary=record.before_summary,
            after_summary=record.after_summary,
            occurred_at=_as_utc(record.occurred_at),
            idempotency_key=record.idempotency_key,
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
