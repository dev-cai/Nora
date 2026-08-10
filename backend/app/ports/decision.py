"""Decision & Reporting 应用层依赖的 Repository 契约。"""

from typing import Protocol
from uuid import UUID

from app.domain.decision import DecisionCase


class DecisionCaseRepository(Protocol):
    """用户范围内 DecisionCase 的幂等创建、生命周期更新与读取端口。"""

    async def add(self, decision_case: DecisionCase) -> DecisionCase: ...

    async def update(self, decision_case: DecisionCase) -> DecisionCase: ...

    async def get_by_id(self, case_id: UUID) -> DecisionCase | None: ...

    async def get_by_input_fingerprint(self, fingerprint: str) -> DecisionCase | None: ...

    async def commit(self) -> None: ...
