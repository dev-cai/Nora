"""Application-owned transaction boundary."""

from typing import Protocol


class Transaction(Protocol):
    """Complete or discard the current database transaction segment."""

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
