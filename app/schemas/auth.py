from datetime import date

from pydantic import BaseModel, EmailStr, Field

from app.schemas.user import UserResponse


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    name: str = Field(min_length=1, max_length=50)
    birth_date: date | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class FindEmailRequest(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    birth_date: date


class FindEmailResponse(BaseModel):
    """가입 이메일을 마스킹해 돌려준다 (전체 노출은 계정 열거에 악용될 수 있다)."""

    email: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str
