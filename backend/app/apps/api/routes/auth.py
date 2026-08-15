"""认证 API。"""

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field

from app.application.identity import IdentityService
from app.apps.api.dependencies.common import get_current_user
from app.apps.api.dependencies.identity import get_identity_service
from app.domain.identity import User
from app.infrastructure.logging import SecurityResult, SecuritySignal, log_security_signal

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    """注册请求。"""

    username: str = Field(min_length=3, max_length=64)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=256)


class LoginRequest(BaseModel):
    """登录请求。"""

    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserResponse(BaseModel):
    """不包含密码的用户响应。"""

    id: str
    username: str
    email: str

    @classmethod
    def from_user(cls, user: User) -> "UserResponse":
        return cls(id=str(user.id), username=user.username, email=user.email)


class TokenResponse(BaseModel):
    """访问令牌响应。"""

    access_token: str
    token_type: str = "bearer"


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    service: IdentityService = Depends(get_identity_service),
) -> UserResponse:
    user = await service.register(payload.username, payload.email, payload.password)
    return UserResponse.from_user(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    service: IdentityService = Depends(get_identity_service),
) -> TokenResponse:
    token = await service.login(
        payload.username,
        payload.password,
        getattr(request.state, "client_identifier", "direct"),
    )
    log_security_signal(
        SecuritySignal.LOGIN,
        SecurityResult.SUCCEEDED,
        request_id=getattr(request.state, "request_id", None),
        trusted_proxy=getattr(request.state, "trusted_proxy", False),
    )
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.from_user(user)
