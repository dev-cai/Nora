"""用户身份领域规则。"""

from dataclasses import dataclass
from uuid import UUID, uuid4

from app.domain.base.exceptions import DomainError


@dataclass(frozen=True, slots=True)
class User:
    """不包含密码的用户身份。"""

    id: UUID
    username: str
    email: str

    @classmethod
    def create(cls, username: str, email: str) -> "User":
        normalized_username = username.strip().lower()
        normalized_email = email.strip().lower()
        if not 3 <= len(normalized_username) <= 64:
            raise DomainError(
                "Username must contain 3-64 characters", error_code="invalid_username"
            )
        if any(char.isspace() for char in normalized_username):
            raise DomainError("Username cannot contain whitespace", error_code="invalid_username")
        local_part, separator, domain = normalized_email.partition("@")
        if (
            not separator
            or not local_part
            or not domain
            or "@" in domain
            or any(char.isspace() for char in normalized_email)
            or len(normalized_email) > 320
        ):
            raise DomainError("Email address is invalid", error_code="invalid_email")
        return cls(id=uuid4(), username=normalized_username, email=normalized_email)
