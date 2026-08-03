from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserResponse, WithdrawRequest
from app.services import user_service
from app.services.s3_storage import S3Storage, get_s3_storage

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def withdraw(
    payload: WithdrawRequest,
    db: Session = Depends(get_db),
    s3: S3Storage = Depends(get_s3_storage),
    current_user: User = Depends(get_current_user),
) -> None:
    """탈퇴: 관련 DB 데이터와 S3 사진 원본을 함께 하드 삭제한다."""
    user_service.withdraw(db, s3, current_user, payload.password)
