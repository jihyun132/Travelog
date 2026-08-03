from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.diary import DiaryResponse, DiaryUpsert
from app.services import diary_service

router = APIRouter(prefix="/places/{place_id}/diary", tags=["diaries"])


@router.put("", response_model=DiaryResponse)
def upsert_diary(
    place_id: int,
    payload: DiaryUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DiaryResponse:
    """일기 작성/수정. 방문지당 1개 — 이미 있으면 덮어쓴다."""
    diary = diary_service.upsert_diary(db, current_user, place_id, payload)
    return DiaryResponse.model_validate(diary)


@router.get("", response_model=DiaryResponse)
def get_diary(
    place_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DiaryResponse:
    return DiaryResponse.model_validate(diary_service.get_diary(db, current_user, place_id))


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_diary(
    place_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    diary_service.delete_diary(db, current_user, place_id)
