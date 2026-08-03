from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import UnauthorizedError
from app.core.security import verify_password
from app.models.photo import Photo
from app.models.user import User
from app.services.s3_storage import S3Storage


def withdraw(db: Session, s3: S3Storage, user: User, password: str | None) -> None:
    """회원 탈퇴: 비밀번호 재확인 후 관련 데이터 즉시 하드 삭제 (SRS 2.1.1~2.1.3).

    refresh_tokens, trips, places, photos, diaries 등 하위 데이터는 FK ON DELETE CASCADE로
    함께 삭제되어 모든 Refresh 토큰이 무효화된다. soft delete 금지.

    DB 행만 지우면 S3 원본이 고아로 남으므로, 사진 바이트도 함께 삭제한다.
    presign 시점에 s3_key와 photos 행이 같이 만들어지므로 행을 훑으면 모든 객체가 커버된다.
    S3 삭제를 먼저 하고 DB를 지운다 — 중간에 실패하면 계정이 남아 재시도할 수 있다.
    """
    if user.password_hash is not None:
        if not password or not verify_password(password, user.password_hash):
            raise UnauthorizedError("비밀번호가 올바르지 않습니다.")
    # 소셜 전용 가입자(password_hash 없음)는 access 토큰 인증만으로 탈퇴 가능

    s3_keys = list(db.scalars(select(Photo.s3_key).where(Photo.user_id == user.id)))
    if s3_keys:
        s3.delete_objects(s3_keys)

    db.delete(user)
    db.commit()
