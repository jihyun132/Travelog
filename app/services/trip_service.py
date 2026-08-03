from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, UnprocessableError
from app.models.diary import Diary
from app.models.photo import Photo
from app.models.place import Place
from app.models.trip import Trip
from app.models.user import User
from app.schemas.globe import GlobePlace, GlobeResponse, GlobeTrip
from app.schemas.trip import TripCreate, TripUpdate


@dataclass
class TripSummary:
    """목록·카드 렌더링에 필요한 집계값 묶음. 사진 전체를 실어보내지 않기 위한 것이다."""

    trip: Trip
    place_count: int
    photo_count: int
    last_taken_at: datetime | None
    thumbnail: Photo | None


def get_own_trip(db: Session, user: User, trip_id: int) -> Trip:
    trip = db.get(Trip, trip_id)
    if trip is None or trip.user_id != user.id:
        raise NotFoundError("여행을 찾을 수 없습니다.")
    return trip


def create_trip(db: Session, user: User, payload: TripCreate) -> Trip:
    trip = Trip(user_id=user.id, **payload.model_dump())
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip


def update_trip(db: Session, user: User, trip_id: int, payload: TripUpdate) -> Trip:
    trip = get_own_trip(db, user, trip_id)
    fields = payload.model_dump(exclude_unset=True)

    # 대표사진은 이 여행에 속한 사진만 지정할 수 있다.
    cover_photo_id = fields.get("cover_photo_id")
    if cover_photo_id is not None and not _owns_photo(db, trip, cover_photo_id):
        raise UnprocessableError("이 여행의 사진만 대표사진으로 지정할 수 있습니다.")

    for key, value in fields.items():
        setattr(trip, key, value)

    # 부분 수정이라 병합 후의 기간을 검증해야 한다.
    if trip.start_date and trip.end_date and trip.start_date > trip.end_date:
        raise UnprocessableError("종료일은 시작일보다 빠를 수 없습니다.")

    db.commit()
    db.refresh(trip)
    return trip


def _owns_photo(db: Session, trip: Trip, photo_id: int) -> bool:
    return (
        db.scalar(
            select(Photo.id)
            .join(Place, Photo.place_id == Place.id)
            .where(Photo.id == photo_id, Place.trip_id == trip.id)
        )
        is not None
    )


def delete_trip(db: Session, user: User, trip_id: int) -> None:
    """여행 삭제. 방문지는 CASCADE로 함께 삭제되고 사진은 미분류로 남는다."""
    trip = get_own_trip(db, user, trip_id)
    place_ids = list(db.scalars(select(Place.id).where(Place.trip_id == trip.id)))
    if place_ids:
        # FK가 SET NULL이지만 sort_order까지 정리하려면 명시적으로 비워야 한다.
        for photo in db.scalars(select(Photo).where(Photo.place_id.in_(place_ids))):
            photo.place_id = None
            photo.sort_order = None
        db.flush()
    db.delete(trip)
    db.commit()


def _thumbnail_photo(db: Session, trip: Trip) -> Photo | None:
    """여행 대표 사진: 사용자가 지정한 대표사진, 없으면 경로상 첫 방문지의 첫 사진."""
    if trip.cover_photo_id is not None:
        cover = db.get(Photo, trip.cover_photo_id)
        if cover is not None:
            return cover

    return db.scalars(
        select(Photo)
        .join(Place, Photo.place_id == Place.id)
        .where(Place.trip_id == trip.id)
        .order_by(
            Place.visit_order,
            Photo.sort_order.asc().nulls_last(),
            Photo.taken_at.asc().nulls_last(),
            Photo.id,
        )
        .limit(1)
    ).first()


def get_trip_summary(db: Session, trip: Trip) -> TripSummary:
    """카드 렌더링용 집계 한 건 (방문지 수·사진 수·마지막 촬영일·대표 사진)."""
    place_count = db.scalar(select(func.count()).select_from(Place).where(Place.trip_id == trip.id))
    photo_count, last_taken_at = db.execute(
        select(func.count(Photo.id), func.max(Photo.taken_at))
        .join(Place, Photo.place_id == Place.id)
        .where(Place.trip_id == trip.id)
    ).one()
    return TripSummary(
        trip=trip,
        place_count=place_count or 0,
        photo_count=photo_count or 0,
        last_taken_at=last_taken_at,
        thumbnail=_thumbnail_photo(db, trip),
    )


def list_trips(db: Session, user: User) -> list[TripSummary]:
    """내 여행 목록 집계. 최근 생성 순."""
    trips = list(
        db.scalars(
            select(Trip).where(Trip.user_id == user.id).order_by(Trip.created_at.desc(), Trip.id)
        )
    )
    return [get_trip_summary(db, trip) for trip in trips]


def list_trip_diaries(db: Session, trip: Trip) -> list[Diary]:
    """여행에 속한 모든 방문지의 일기. 상세 화면이 방문지별로 다시 묻지 않도록 함께 내려준다."""
    return list(
        db.scalars(
            select(Diary)
            .join(Place, Diary.place_id == Place.id)
            .where(Place.trip_id == trip.id)
            .order_by(Place.visit_order, Diary.id)
        )
    )


def get_globe_data(db: Session, user: User) -> GlobeResponse:
    """지구본 렌더링용 일괄 조회 (SRS 1.1~1.2).

    여행 1회 + 방문지 1회, 총 2번의 쿼리로 끝내 N+1을 피한다.
    """
    trips = list(
        db.scalars(select(Trip).where(Trip.user_id == user.id).order_by(Trip.created_at, Trip.id))
    )
    if not trips:
        return GlobeResponse(trips=[])

    places = db.scalars(
        select(Place)
        .where(Place.trip_id.in_([trip.id for trip in trips]))
        .order_by(Place.visit_order, Place.id)
    )
    places_by_trip: dict[int, list[GlobePlace]] = {trip.id: [] for trip in trips}
    for place in places:
        places_by_trip[place.trip_id].append(GlobePlace.model_validate(place))

    return GlobeResponse(
        trips=[
            GlobeTrip(
                id=trip.id,
                title=trip.title,
                start_date=trip.start_date,
                end_date=trip.end_date,
                places=places_by_trip[trip.id],
            )
            for trip in trips
        ]
    )
