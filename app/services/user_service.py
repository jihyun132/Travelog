from sqlalchemy.orm import Session

from app.core.exceptions import UnauthorizedError
from app.core.security import verify_password
from app.models.user import User


def withdraw(db: Session, user: User, password: str | None) -> None:
    """회원 탈퇴: 비밀번호 재확인 후 관련 데이터 즉시 하드 삭제 (SRS 2.1.1~2.1.3).

    refresh_tokens, photo_locations 등 하위 데이터는 FK ON DELETE CASCADE로 함께 삭제되어
    모든 Refresh 토큰이 무효화된다. soft delete 금지.
    """
    if user.password_hash is not None:
        if not password or not verify_password(password, user.password_hash):
            raise UnauthorizedError("비밀번호가 올바르지 않습니다.")
    # Kakao 전용 가입자(password_hash 없음)는 access 토큰 인증만으로 탈퇴 가능

    db.delete(user)
    db.commit()
