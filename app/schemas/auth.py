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


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class KakaoLoginRequest(BaseModel):
    code: str
    # 앱/웹 등 클라이언트별 redirect_uri가 다를 수 있어 요청에서 받는다. 없으면 서버 설정값 사용.
    redirect_uri: str | None = None
