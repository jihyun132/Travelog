from datetime import UTC, date, datetime, timedelta

from jose import JWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError, UnauthorizedError
from app.core.security import (
    TOKEN_TYPE_REFRESH,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import LoginRequest, SignupRequest


def signup(db: Session, payload: SignupRequest) -> User:
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise ConflictError("이미 가입된 이메일입니다.")

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        name=payload.name,
        birth_date=payload.birth_date,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _mask_email(email: str) -> str:
    """앞 2자만 남기고 가린다: traveler@x.com → tr******@x.com"""
    local, _, domain = email.partition("@")
    visible = local[:2]
    return f"{visible}{'*' * max(len(local) - len(visible), 1)}@{domain}"


def find_email(db: Session, name: str, birth_date: date) -> str:
    """SRS 0.2.5 - 이름 + 생년월일로 가입 이메일을 찾아 마스킹해 반환한다."""
    user = db.scalar(select(User).where(User.name == name.strip(), User.birth_date == birth_date))
    if user is None:
        raise NotFoundError("일치하는 계정을 찾을 수 없습니다.")
    return _mask_email(user.email)


def _issue_tokens(db: Session, user: User) -> tuple[str, str]:
    """Access/Refresh 토큰을 발급하고 Refresh는 DB에 저장한다."""
    settings = get_settings()
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    db.add(
        RefreshToken(
            user_id=user.id,
            token=refresh_token,
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    db.commit()
    return access_token, refresh_token


def login(db: Session, payload: LoginRequest) -> tuple[User, str, str]:
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None or user.password_hash is None:
        raise UnauthorizedError("이메일 또는 비밀번호가 올바르지 않습니다.")
    if not verify_password(payload.password, user.password_hash):
        raise UnauthorizedError("이메일 또는 비밀번호가 올바르지 않습니다.")

    access_token, refresh_token = _issue_tokens(db, user)
    return user, access_token, refresh_token


def refresh(db: Session, refresh_token: str) -> tuple[User, str, str]:
    """Refresh 토큰 검증 후 새 토큰 쌍 발급(rotation: 기존 토큰은 폐기)."""
    try:
        payload = decode_token(refresh_token, TOKEN_TYPE_REFRESH)
    except JWTError:
        raise UnauthorizedError("유효하지 않은 Refresh 토큰입니다.") from None

    stored = db.scalar(select(RefreshToken).where(RefreshToken.token == refresh_token))
    if stored is None:
        raise UnauthorizedError("이미 사용되었거나 무효화된 Refresh 토큰입니다.")

    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise UnauthorizedError("존재하지 않는 사용자입니다.")

    db.delete(stored)
    access_token, new_refresh_token = _issue_tokens(db, user)
    return user, access_token, new_refresh_token


def logout(db: Session, user: User, refresh_token: str) -> None:
    """본인 소유의 Refresh 토큰을 무효화한다. 이미 없으면 조용히 성공 처리."""
    stored = db.scalar(
        select(RefreshToken).where(
            RefreshToken.token == refresh_token, RefreshToken.user_id == user.id
        )
    )
    if stored is not None:
        db.delete(stored)
        db.commit()
