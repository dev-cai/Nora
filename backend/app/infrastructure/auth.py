"""密码哈希和 JWT 适配器。"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import PwdlibError

from app.domain.base.exceptions import ErrorCode, NoraError


class Argon2PasswordHasher:
    """使用 pwdlib 推荐的 Argon2id 参数。"""

    def __init__(self) -> None:
        self._password_hash = PasswordHash.recommended()

    def hash(self, password: str) -> str:
        return self._password_hash.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        try:
            return self._password_hash.verify(password, password_hash)
        except PwdlibError:
            return False


class JwtTokenIssuer:
    """短时效 Bearer JWT 适配器。"""

    def __init__(self, secret_key: str, access_token_minutes: int) -> None:
        if len(secret_key.encode("utf-8")) < 32:
            raise ValueError("JWT secret key must contain at least 32 bytes")
        if access_token_minutes <= 0:
            raise ValueError("JWT access token lifetime must be positive")
        self.secret_key = secret_key
        self.access_token_minutes = access_token_minutes

    def issue(self, user_id: UUID) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user_id),
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=self.access_token_minutes),
        }
        return jwt.encode(payload, self.secret_key, algorithm="HS256")

    def decode(self, token: str) -> UUID:
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=["HS256"],
                options={"require": ["sub", "type", "iat", "exp"]},
            )
            if payload.get("type") != "access":
                raise ValueError("invalid token type")
            return UUID(str(payload["sub"]))
        except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as exc:
            raise NoraError(
                "Authentication required", error_code=ErrorCode.AUTHENTICATION_FAILED
            ) from exc
