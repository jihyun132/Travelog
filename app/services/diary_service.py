from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.diary import Diary
from app.models.user import User
from app.schemas.diary import DiaryUpsert
from app.services import photo_group_service


def _find_diary(db: Session, group_id: int) -> Diary | None:
    return db.scalars(select(Diary).where(Diary.group_id == group_id)).first()


def get_diary(db: Session, user: User, group_id: int) -> Diary:
    photo_group_service.get_own_group(db, user, group_id)
    diary = _find_diary(db, group_id)
    if diary is None:
        raise NotFoundError("일기를 찾을 수 없습니다.")
    return diary


def upsert_diary(db: Session, user: User, group_id: int, payload: DiaryUpsert) -> Diary:
    """일기가 없으면 생성, 있으면 내용·날씨를 덮어쓴다 (그룹당 1개)."""
    group = photo_group_service.get_own_group(db, user, group_id)
    diary = _find_diary(db, group.id)
    if diary is None:
        diary = Diary(user_id=user.id, group_id=group.id, **payload.model_dump())
        db.add(diary)
    else:
        diary.content = payload.content
        diary.weather = payload.weather
    db.commit()
    db.refresh(diary)
    return diary


def delete_diary(db: Session, user: User, group_id: int) -> None:
    diary = get_diary(db, user, group_id)
    db.delete(diary)
    db.commit()
