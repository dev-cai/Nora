"""Identity 领域和令牌单元测试。"""

from uuid import uuid4

import jwt
import pytest
from app.application.identity import IdentityService
from app.application.identity.service import DUMMY_PASSWORD_HASH
from app.domain.base.exceptions import DomainError, NoraError
from app.domain.identity import User
from app.infrastructure.auth import Argon2PasswordHasher, JwtTokenIssuer
from app.ports.identity import AccessTokenClaims, StoredCredential


class StubUserRepository:
    def __init__(self, credential: StoredCredential | None) -> None:
        self.credential = credential

    async def add(self, user: User, password_hash: str) -> User:
        raise AssertionError("login must not add a user")

    async def get_by_username(self, username: str) -> StoredCredential | None:
        return self.credential

    async def get_by_id(self, user_id: object) -> User | None:
        raise AssertionError("login must not load a user by id")

    async def exists_by_email(self, email: str) -> bool:
        raise AssertionError("login must not inspect email availability")

    async def commit(self) -> None:
        raise AssertionError("failed login must not commit user state")


class RecordingPasswordHasher:
    def __init__(self) -> None:
        self.verifications: list[tuple[str, str]] = []

    def hash(self, password: str) -> str:
        raise AssertionError("login must not hash a password")

    def verify(self, password: str, password_hash: str) -> bool:
        self.verifications.append((password, password_hash))
        return False


class RejectingTokenIssuer:
    def issue(self, user_id: object, session_version: int = 1) -> str:
        raise AssertionError("failed login must not issue a token")

    def decode(self, token: str) -> AccessTokenClaims:
        raise AssertionError("login must not decode a token")


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
    claims = issuer.decode(token)
    assert claims.session_version == 1
    assert claims.kid == "dev"

    with pytest.raises(NoraError, match="Authentication required"):
        issuer.decode("not-a-token")

    incomplete_token = jwt.encode(
        {"sub": str(user_id), "type": "access"}, issuer.secret_key, algorithm="HS256"
    )
    with pytest.raises(NoraError, match="Authentication required"):
        issuer.decode(incomplete_token)


def test_password_hasher_rejects_malformed_hash() -> None:
    assert Argon2PasswordHasher().verify("password-123", "not-a-password-hash") is False


@pytest.mark.asyncio
async def test_unknown_user_uses_dummy_hash_and_matches_wrong_password_failure() -> None:
    known_user = User.create("alice", "alice@example.com")
    known_hasher = RecordingPasswordHasher()
    unknown_hasher = RecordingPasswordHasher()
    known_service = IdentityService(
        StubUserRepository(StoredCredential(known_user, "stored-password-hash")),
        known_hasher,
        RejectingTokenIssuer(),
    )
    unknown_service = IdentityService(
        StubUserRepository(None),
        unknown_hasher,
        RejectingTokenIssuer(),
    )

    with pytest.raises(NoraError) as known_error:
        await known_service.login("alice", "wrong-password")
    with pytest.raises(NoraError) as unknown_error:
        await unknown_service.login("unknown", "wrong-password")

    assert known_error.value.error_code == "authentication_failed"
    assert unknown_error.value.error_code == known_error.value.error_code
    assert str(unknown_error.value) == str(known_error.value)
    assert known_hasher.verifications == [("wrong-password", "stored-password-hash")]
    assert unknown_hasher.verifications == [("wrong-password", DUMMY_PASSWORD_HASH)]


def test_jwt_issuer_rejects_unsafe_configuration() -> None:
    with pytest.raises(ValueError, match="at least 32 bytes"):
        JwtTokenIssuer("too-short", access_token_minutes=5)
    with pytest.raises(ValueError, match="must be positive"):
        JwtTokenIssuer("test-secret-32-bytes-long-key-value!", access_token_minutes=0)


def test_jwt_key_rotation_keeps_overlap_and_emergency_removal_revokes() -> None:
    old_key = "old-test-secret-key-with-32-bytes!"
    new_key = "new-test-secret-key-with-32-bytes!"
    user_id = uuid4()
    old_token = JwtTokenIssuer(
        access_token_minutes=5,
        key_ring={"old": old_key},
        active_kid="old",
    ).issue(user_id, session_version=3)

    overlapping = JwtTokenIssuer(
        access_token_minutes=5,
        key_ring={"old": old_key, "new": new_key},
        active_kid="new",
    )
    assert overlapping.decode(old_token).session_version == 3
    assert overlapping.decode(overlapping.issue(user_id, 3)).kid == "new"

    emergency = JwtTokenIssuer(
        access_token_minutes=5,
        key_ring={"new": new_key},
        active_kid="new",
    )
    with pytest.raises(NoraError, match="Authentication required"):
        emergency.decode(old_token)
