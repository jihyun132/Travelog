from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.exceptions import UnauthorizedError
from app.core.security import TOKEN_TYPE_ACCESS, decode_token
from app.db.session import get_db
from app.models.user import User

# auto_error=False: 게스트(비인증) 요청을 401로 즉시 끊지 않고 optional 의존성에서 분기한다.
_bearer = HTTPBearer(auto_error=False)


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User | None:
    """게스트 허용 API용. 토큰이 없으면 None, 있는데 유효하지 않으면 401."""
    if credentials is None:
        return None
    try:
        payload = decode_token(credentials.credentials, TOKEN_TYPE_ACCESS)
    except JWTError:
        raise UnauthorizedError("유효하지 않은 토큰입니다.") from None
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise UnauthorizedError("존재하지 않는 사용자입니다.")
    return user


def get_current_user(
    user: User | None = Depends(get_current_user_optional),
) -> User:
    """인증 필수 API용. 게스트는 401."""
    if user is None:
        raise UnauthorizedError("로그인이 필요합니다.")
    return user
