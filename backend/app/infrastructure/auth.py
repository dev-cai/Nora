"""Password hashing, anonymous authentication identifiers and JWT key-ring adapter."""

import hashlib
import hmac
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import PwdlibError

from app.domain.base.exceptions import ErrorCode, NoraError
from app.ports.identity import AccessTokenClaims

JWT_ISSUER = "nora-api"
JWT_AUDIENCE = "nora-web"
JWT_CLOCK_SKEW_SECONDS = 30
KID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,64}")


class Argon2PasswordHasher:
    """Use pwdlib's recommended Argon2id parameters and fail malformed hashes closed."""

    def __init__(self) -> None:
        self._password_hash = PasswordHash.recommended()

    def hash(self, password: str) -> str:
        return self._password_hash.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        try:
            return self._password_hash.verify(password, password_hash)
        except PwdlibError:
            return False


class AuthenticationDigester:
    """Create non-reversible, dimension-separated identifiers for security buckets."""

    def __init__(self, secret: str) -> None:
        if len(secret.encode("utf-8")) < 32:
            raise ValueError("Authentication rate-limit secret must contain at least 32 bytes")
        self._secret = secret.encode("utf-8")

    def digest(self, dimension: str, value: str) -> str:
        payload = f"{dimension}\0{value}".encode("utf-8")
        return hmac.new(self._secret, payload, hashlib.sha256).hexdigest()


class JwtTokenIssuer:
    """Short-lived HS256 JWT using a fixed verification key allowlist."""

    def __init__(
        self,
        secret_key: str | None = None,
        access_token_minutes: int = 30,
        *,
        key_ring: dict[str, str] | None = None,
        active_kid: str = "dev",
    ) -> None:
        configured_ring = dict(key_ring or ({active_kid: secret_key} if secret_key else {}))
        if not configured_ring:
            raise ValueError("JWT key ring must not be empty")
        if KID_PATTERN.fullmatch(active_kid) is None or active_kid not in configured_ring:
            raise ValueError("JWT active kid must identify a configured safe key")
        if any(
            KID_PATTERN.fullmatch(kid) is None or len(secret.encode("utf-8")) < 32
            for kid, secret in configured_ring.items()
        ):
            raise ValueError("JWT keys must use safe kid values and contain at least 32 bytes")
        if access_token_minutes <= 0:
            raise ValueError("JWT access token lifetime must be positive")
        if access_token_minutes > 30:
            raise ValueError("JWT access token lifetime must not exceed 30 minutes")
        self._key_ring = configured_ring
        self.active_kid = active_kid
        self.access_token_minutes = access_token_minutes

    @property
    def secret_key(self) -> str:
        """Compatibility accessor for deterministic unit fixtures."""

        return self._key_ring[self.active_kid]

    def issue(self, user_id: UUID, session_version: int = 1) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user_id),
            "type": "access",
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=self.access_token_minutes),
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "session_version": session_version,
        }
        return jwt.encode(
            payload,
            self.secret_key,
            algorithm="HS256",
            headers={"kid": self.active_kid},
        )

    def decode(self, token: str) -> AccessTokenClaims:
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if not isinstance(kid, str) or KID_PATTERN.fullmatch(kid) is None:
                raise ValueError("invalid kid")
            secret = self._key_ring.get(kid)
            if secret is None:
                raise ValueError("unknown kid")
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                issuer=JWT_ISSUER,
                audience=JWT_AUDIENCE,
                leeway=JWT_CLOCK_SKEW_SECONDS,
                options={
                    "require": [
                        "sub",
                        "type",
                        "iat",
                        "nbf",
                        "exp",
                        "iss",
                        "aud",
                        "session_version",
                    ]
                },
            )
            session_version = payload["session_version"]
            issued_at = payload["iat"]
            expires_at = payload["exp"]
            if (
                payload.get("type") != "access"
                or isinstance(session_version, bool)
                or not isinstance(session_version, int)
                or session_version < 1
                or not isinstance(issued_at, (int, float))
                or not isinstance(expires_at, (int, float))
                or expires_at - issued_at > self.access_token_minutes * 60
            ):
                raise ValueError("invalid token claims")
            return AccessTokenClaims(UUID(str(payload["sub"])), session_version, kid)
        except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as exc:
            raise NoraError(
                "Authentication required", error_code=ErrorCode.AUTHENTICATION_FAILED
            ) from exc
