from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    name: str
    birth_date: date | None
    created_at: datetime


class WithdrawRequest(BaseModel):
    # Kakao 전용 가입자는 비밀번호가 없으므로 생략 가능. 이메일 가입자는 필수 검증.
    password: str | None = None
