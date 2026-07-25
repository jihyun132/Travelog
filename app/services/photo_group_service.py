from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import NotFoundError, UnprocessableError
from app.core.geo import haversine_m
from app.models.photo import Photo, PhotoStatus
from app.models.photo_group import PhotoGroup
from app.models.user import User
from app.schemas.photo_group import PhotoGroupCreate, PhotoGroupUpdate

# 그룹 내 사진 기본 정렬: 사용자 지정 순서 → 촬영일시 → id
_PHOTO_ORDER = (
    Photo.sort_order.asc().nulls_last(),
    Photo.taken_at.asc().nulls_last(),
    Photo.id,
)


def _radius_m(group: PhotoGroup) -> int:
    return group.radius_m or get_settings().default_group_radius_m


def find_group_in_radius(
    db: Session, user_id: int, latitude: float, longitude: float
) -> PhotoGroup | None:
    """반경 이내 그룹 중 가장 가까운 그룹. 없으면 None(미분류)."""
    groups = db.scalars(select(PhotoGroup).where(PhotoGroup.user_id == user_id))
    best: PhotoGroup | None = None
    best_dist = float("inf")
    for group in groups:
        dist = haversine_m(latitude, longitude, group.anchor_lat, group.anchor_lng)
        if dist <= _radius_m(group) and dist < best_dist:
            best, best_dist = group, dist
    return best


def _absorb_unassigned(db: Session, group: PhotoGroup) -> None:
    """미분류 완료 사진 중 반경 이내인 것을 이 그룹으로 편입한다."""
    photos = db.scalars(
        select(Photo).where(
            Photo.user_id == group.user_id,
            Photo.group_id.is_(None),
            Photo.status == PhotoStatus.COMPLETED,
            Photo.latitude.is_not(None),
        )
    )
    radius = _radius_m(group)
    for photo in photos:
        if (
            haversine_m(photo.latitude, photo.longitude, group.anchor_lat, group.anchor_lng)
            <= radius
        ):
            photo.group_id = group.id


def _release_out_of_radius(db: Session, group: PhotoGroup) -> None:
    """앵커·반경 변경 후 반경을 벗어난 소속 사진을 미분류로 되돌린다."""
    photos = db.scalars(select(Photo).where(Photo.group_id == group.id))
    radius = _radius_m(group)
    for photo in photos:
        if (
            photo.latitude is None
            or haversine_m(photo.latitude, photo.longitude, group.anchor_lat, group.anchor_lng)
            > radius
        ):
            photo.group_id = None
            photo.sort_order = None


def get_own_group(db: Session, user: User, group_id: int) -> PhotoGroup:
    group = db.get(PhotoGroup, group_id)
    if group is None or group.user_id != user.id:
        raise NotFoundError("그룹을 찾을 수 없습니다.")
    return group


def create_group(db: Session, user: User, payload: PhotoGroupCreate) -> PhotoGroup:
    group = PhotoGroup(user_id=user.id, **payload.model_dump())
    db.add(group)
    db.flush()  # id 확보
    _absorb_unassigned(db, group)
    db.commit()
    db.refresh(group)
    return group


def update_group(db: Session, user: User, group_id: int, payload: PhotoGroupUpdate) -> PhotoGroup:
    group = get_own_group(db, user, group_id)
    fields = payload.model_dump(exclude_unset=True)
    for key, value in fields.items():
        setattr(group, key, value)

    if fields.keys() & {"anchor_lat", "anchor_lng", "radius_m"}:
        _release_out_of_radius(db, group)
        _absorb_unassigned(db, group)

    db.commit()
    db.refresh(group)
    return group


def delete_group(db: Session, user: User, group_id: int) -> None:
    """그룹만 삭제하고 소속 사진은 미분류로 되돌린다."""
    group = get_own_group(db, user, group_id)
    for photo in db.scalars(select(Photo).where(Photo.group_id == group.id)):
        photo.group_id = None
        photo.sort_order = None
    db.delete(group)
    db.commit()


def list_groups(db: Session, user: User) -> list[tuple[PhotoGroup, int, Photo | None]]:
    """(그룹, 사진 수, 대표 사진) 목록. 대표 사진은 정렬상 첫 사진."""
    groups = list(
        db.scalars(select(PhotoGroup).where(PhotoGroup.user_id == user.id).order_by(PhotoGroup.id))
    )
    result = []
    for group in groups:
        count = db.scalar(select(func.count()).select_from(Photo).where(Photo.group_id == group.id))
        first_photo = db.scalars(
            select(Photo).where(Photo.group_id == group.id).order_by(*_PHOTO_ORDER).limit(1)
        ).first()
        result.append((group, count or 0, first_photo))
    return result


def list_group_photos(db: Session, group: PhotoGroup) -> list[Photo]:
    return list(db.scalars(select(Photo).where(Photo.group_id == group.id).order_by(*_PHOTO_ORDER)))


def update_photo_order(db: Session, user: User, group_id: int, photo_ids: list[int]) -> list[Photo]:
    """사용자가 조정한 순서(전체 ID 배열)를 sort_order로 일괄 저장한다."""
    group = get_own_group(db, user, group_id)
    photos = list_group_photos(db, group)

    current_ids = {photo.id for photo in photos}
    if len(photo_ids) != len(set(photo_ids)) or set(photo_ids) != current_ids:
        raise UnprocessableError("사진 순서 목록이 그룹의 사진과 일치하지 않습니다.")

    order_by_id = {photo_id: index for index, photo_id in enumerate(photo_ids)}
    for photo in photos:
        photo.sort_order = order_by_id[photo.id]
    db.commit()

    return list_group_photos(db, group)
