"""Controlled single-owner bootstrap and credential recovery use cases."""

import hashlib
from typing import Protocol

from app.application.identity.service import PasswordHasher
from app.domain.base.exceptions import ErrorCode, NoraError
from app.domain.identity import User
from app.ports.identity import ManagementResult


class IdentityManagementRepository(Protocol):
    async def bootstrap(
        self,
        user: User,
        password_hash: str,
        request_identity: str,
        identity_fingerprint: str,
    ) -> ManagementResult: ...

    async def recover(
        self, password_hash: str, request_identity: str
    ) -> ManagementResult: ...


class IdentityManagementService:
    """Application boundary used only by the non-HTTP operator command."""

    def __init__(
        self, repository: IdentityManagementRepository, password_hasher: PasswordHasher
    ) -> None:
        self.repository = repository
        self.password_hasher = password_hasher

    async def bootstrap_owner(
        self, request_identity: str, username: str, email: str, password: str
    ) -> ManagementResult:
        request_id = _request_identity(request_identity)
        _validate_password(password)
        user = User.create(username, email)
        fingerprint = hashlib.sha256(
            f"{user.username}\0{user.email}".encode("utf-8")
        ).hexdigest()
        return await self.repository.bootstrap(
            user, self.password_hasher.hash(password), request_id, fingerprint
        )

    async def recover_credentials(
        self, request_identity: str, password: str
    ) -> ManagementResult:
        request_id = _request_identity(request_identity)
        _validate_password(password)
        return await self.repository.recover(self.password_hasher.hash(password), request_id)


def _request_identity(value: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 255:
        raise NoraError(
            "Management request identity is invalid", error_code=ErrorCode.INVALID_IDEMPOTENCY_KEY
        )
    return normalized


def _validate_password(password: str) -> None:
    if not 8 <= len(password) <= 256:
        raise NoraError(
            "Password must contain 8-256 characters", error_code=ErrorCode.INVALID_PASSWORD
        )
