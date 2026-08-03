from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import NotFoundError, UnprocessableError
from app.core.geo import haversine_m
from app.models.photo import Photo, PhotoStatus
from app.models.place import Place
from app.models.trip import Trip
from app.models.user import User
from app.schemas.place import PlaceCreate, PlaceUpdate

# 방문지 내 사진 기본 정렬: 사용자 지정 순서 → 촬영일시 → id
_PHOTO_ORDER = (
    Photo.sort_order.asc().nulls_last(),
    Photo.taken_at.asc().nulls_last(),
    Photo.id,
)


def _radius_m(place: Place) -> int:
    return place.radius_m or get_settings().default_place_radius_m


def find_place_in_radius(
    db: Session, user_id: int, latitude: float, longitude: float
) -> Place | None:
    """반경 이내 방문지 중 가장 가까운 곳. 없으면 None(미분류).

    여행과 무관하게 사용자의 모든 방문지를 대상으로 한다.
    """
    places = db.scalars(select(Place).where(Place.user_id == user_id))
    best: Place | None = None
    best_dist = float("inf")
    for place in places:
        dist = haversine_m(latitude, longitude, place.anchor_lat, place.anchor_lng)
        if dist <= _radius_m(place) and dist < best_dist:
            best, best_dist = place, dist
    return best


def _absorb_unassigned(db: Session, place: Place) -> None:
    """미분류 완료 사진 중 반경 이내인 것을 이 방문지로 편입한다."""
    photos = db.scalars(
        select(Photo).where(
            Photo.user_id == place.user_id,
            Photo.place_id.is_(None),
            Photo.status == PhotoStatus.COMPLETED,
            Photo.latitude.is_not(None),
        )
    )
    radius = _radius_m(place)
    for photo in photos:
        if (
            haversine_m(photo.latitude, photo.longitude, place.anchor_lat, place.anchor_lng)
            <= radius
        ):
            photo.place_id = place.id


def _release_out_of_radius(db: Session, place: Place) -> None:
    """앵커·반경 변경 후 반경을 벗어난 소속 사진을 미분류로 되돌린다."""
    photos = db.scalars(select(Photo).where(Photo.place_id == place.id))
    radius = _radius_m(place)
    for photo in photos:
        if (
            photo.latitude is None
            or haversine_m(photo.latitude, photo.longitude, place.anchor_lat, place.anchor_lng)
            > radius
        ):
            photo.place_id = None
            photo.sort_order = None


def _next_visit_order(db: Session, trip_id: int) -> int:
    last = db.scalar(select(func.max(Place.visit_order)).where(Place.trip_id == trip_id))
    return (last or 0) + 1


def _compact_visit_order(db: Session, trip_id: int) -> None:
    """방문지 삭제 후 남은 순서를 1부터 빈틈없이 다시 매긴다."""
    places = db.scalars(
        select(Place).where(Place.trip_id == trip_id).order_by(Place.visit_order, Place.id)
    )
    for index, place in enumerate(places, start=1):
        place.visit_order = index


def get_own_place(db: Session, user: User, place_id: int) -> Place:
    place = db.get(Place, place_id)
    if place is None or place.user_id != user.id:
        raise NotFoundError("방문지를 찾을 수 없습니다.")
    return place


def create_place(db: Session, user: User, trip: Trip, payload: PlaceCreate) -> Place:
    """방문지 생성. 생성 즉시 반경 내 미분류 사진을 편입한다."""
    place = Place(
        user_id=user.id,
        trip_id=trip.id,
        visit_order=_next_visit_order(db, trip.id),
        **payload.model_dump(),
    )
    db.add(place)
    db.flush()  # id 확보
    _absorb_unassigned(db, place)
    db.commit()
    db.refresh(place)
    return place


def update_place(db: Session, user: User, place_id: int, payload: PlaceUpdate) -> Place:
    place = get_own_place(db, user, place_id)
    fields = payload.model_dump(exclude_unset=True)
    for key, value in fields.items():
        setattr(place, key, value)

    if fields.keys() & {"anchor_lat", "anchor_lng", "radius_m"}:
        _release_out_of_radius(db, place)
        _absorb_unassigned(db, place)

    db.commit()
    db.refresh(place)
    return place


def set_visited(db: Session, user: User, place_id: int, is_visited: bool) -> Place:
    """방문 처리 (SRS 1.2.4). 방문 해제 시 visited_at도 지운다."""
    place = get_own_place(db, user, place_id)
    place.is_visited = is_visited
    place.visited_at = datetime.now(UTC) if is_visited else None
    db.commit()
    db.refresh(place)
    return place


def delete_place(db: Session, user: User, place_id: int) -> None:
    """방문지만 삭제하고 소속 사진은 미분류로 되돌린다 (일기는 CASCADE 삭제)."""
    place = get_own_place(db, user, place_id)
    for photo in db.scalars(select(Photo).where(Photo.place_id == place.id)):
        photo.place_id = None
        photo.sort_order = None
    trip_id = place.trip_id
    db.delete(place)
    db.flush()
    _compact_visit_order(db, trip_id)
    db.commit()


def list_places(db: Session, trip: Trip) -> list[tuple[Place, int, Photo | None]]:
    """(방문지, 사진 수, 대표 사진) 목록. 경로 순서(visit_order)로 정렬한다."""
    places = list(
        db.scalars(
            select(Place).where(Place.trip_id == trip.id).order_by(Place.visit_order, Place.id)
        )
    )
    result = []
    for place in places:
        count = db.scalar(select(func.count()).select_from(Photo).where(Photo.place_id == place.id))
        first_photo = db.scalars(
            select(Photo).where(Photo.place_id == place.id).order_by(*_PHOTO_ORDER).limit(1)
        ).first()
        result.append((place, count or 0, first_photo))
    return result


def first_taken_at(db: Session, place: Place) -> datetime | None:
    """방문지의 첫 촬영 시각. 클라이언트의 방문 시각 라벨 표시에 쓰인다."""
    return db.scalar(select(func.min(Photo.taken_at)).where(Photo.place_id == place.id))


def list_place_photos(db: Session, place: Place) -> list[Photo]:
    return list(db.scalars(select(Photo).where(Photo.place_id == place.id).order_by(*_PHOTO_ORDER)))


def update_photo_order(db: Session, user: User, place_id: int, photo_ids: list[int]) -> list[Photo]:
    """사용자가 조정한 순서(전체 ID 배열)를 sort_order로 일괄 저장한다."""
    place = get_own_place(db, user, place_id)
    photos = list_place_photos(db, place)

    current_ids = {photo.id for photo in photos}
    if len(photo_ids) != len(set(photo_ids)) or set(photo_ids) != current_ids:
        raise UnprocessableError("사진 순서 목록이 방문지의 사진과 일치하지 않습니다.")

    order_by_id = {photo_id: index for index, photo_id in enumerate(photo_ids)}
    for photo in photos:
        photo.sort_order = order_by_id[photo.id]
    db.commit()

    return list_place_photos(db, place)


def reorder_places(db: Session, trip: Trip, place_ids: list[int]) -> list[Place]:
    """여행 경로 재정렬 (SRS 1.2.3). 전체 방문지 ID 배열을 받아 visit_order를 다시 매긴다."""
    places = list(db.scalars(select(Place).where(Place.trip_id == trip.id)))

    current_ids = {place.id for place in places}
    if len(place_ids) != len(set(place_ids)) or set(place_ids) != current_ids:
        raise UnprocessableError("방문지 순서 목록이 여행의 방문지와 일치하지 않습니다.")

    order_by_id = {place_id: index for index, place_id in enumerate(place_ids, start=1)}
    for place in places:
        place.visit_order = order_by_id[place.id]
    db.commit()

    return sorted(places, key=lambda place: place.visit_order)
