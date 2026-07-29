"""Identity 领域和令牌单元测试。"""

from uuid import uuid4

import jwt
import pytest

from nora.domain.base.exceptions import DomainError, NoraError
from nora.domain.identity import User
from nora.infrastructure.auth import Argon2PasswordHasher, JwtTokenIssuer


def test_user_normalizes_identity_fields() -> None:
    user = User.create(" Alice ", "Alice@Example.com")
    assert user.username == "alice"
    assert user.email == "alice@example.com"


@pytest.mark.parametrize(
    ("username", "email", "error_code"),
    [
        ("ab", "a@example.com", "invalid_username"),
        ("alice", "invalid", "invalid_email"),
        ("alice", "@@@", "invalid_email"),
        ("alice", "a@exa mple.com", "invalid_email"),
    ],
)
def test_user_rejects_invalid_identity_fields(username: str, email: str, error_code: str) -> None:
    with pytest.raises(DomainError) as error:
        User.create(username, email)
    assert error.value.error_code == error_code


def test_jwt_round_trip_and_invalid_token() -> None:
    issuer = JwtTokenIssuer("test-secret-32-bytes-long-key-value!", access_token_minutes=5)
    user_id = uuid4()
    token = issuer.issue(user_id)
    assert issuer.decode(token) == user_id

    with pytest.raises(NoraError, match="Authentication required"):
        issuer.decode("not-a-token")

    incomplete_token = jwt.encode(
        {"sub": str(user_id), "type": "access"}, issuer.secret_key, algorithm="HS256"
    )
    with pytest.raises(NoraError, match="Authentication required"):
        issuer.decode(incomplete_token)


def test_password_hasher_rejects_malformed_hash() -> None:
    assert Argon2PasswordHasher().verify("password-123", "not-a-password-hash") is False


def test_jwt_issuer_rejects_unsafe_configuration() -> None:
    with pytest.raises(ValueError, match="at least 32 bytes"):
        JwtTokenIssuer("too-short", access_token_minutes=5)
    with pytest.raises(ValueError, match="must be positive"):
        JwtTokenIssuer("test-secret-32-bytes-long-key-value!", access_token_minutes=0)
