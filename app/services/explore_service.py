"""공개 여행 탐색 (SRS 1.4, P2).

공개(is_public) 여행만 다룬다. 조회는 게스트도 허용하고, 내 여행으로 가져오기는 로그인이 필요하다.
"""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.photo import Photo
from app.models.place import Place
from app.models.trip import Trip
from app.models.user import User
from app.schemas.explore import ExplorePlace, ExploreTripDetailResponse, ExploreTripResponse
from app.services.s3_storage import S3Storage

# 검색 결과 상한. 페이지네이션 없이 한 번에 내려주므로 과다 응답을 막는다.
_SEARCH_LIMIT = 30


def _duration_days(trip: Trip) -> int | None:
    if trip.start_date is None or trip.end_date is None:
        return None
    return (trip.end_date - trip.start_date).days + 1


def _thumbnail_url(db: Session, trip: Trip, s3: S3Storage) -> str | None:
    photo = None
    if trip.cover_photo_id is not None:
        photo = db.get(Photo, trip.cover_photo_id)
    if photo is None:
        photo = db.scalars(
            select(Photo)
            .join(Place, Photo.place_id == Place.id)
            .where(Place.trip_id == trip.id)
            .order_by(Place.visit_order, Photo.taken_at.asc().nulls_last(), Photo.id)
            .limit(1)
        ).first()
    return s3.presign_get(photo.s3_key) if photo is not None else None


def _to_response(db: Session, trip: Trip, owner_name: str, s3: S3Storage) -> ExploreTripResponse:
    place_count = db.scalar(select(func.count()).select_from(Place).where(Place.trip_id == trip.id))
    return ExploreTripResponse(
        id=trip.id,
        title=trip.title,
        country=trip.country,
        start_date=trip.start_date,
        end_date=trip.end_date,
        hashtags=trip.hashtags,
        owner_name=owner_name,
        place_count=place_count or 0,
        duration_days=_duration_days(trip),
        thumbnail_url=_thumbnail_url(db, trip, s3),
    )


def search_trips(db: Session, s3: S3Storage, keyword: str) -> list[ExploreTripResponse]:
    """제목·국가·해시태그·방문지명으로 공개 여행을 찾는다. 빈 키워드는 빈 결과."""
    trimmed = keyword.strip()
    if not trimmed:
        return []

    pattern = f"%{trimmed.lower()}%"
    # 방문지명으로도 찾을 수 있어야 한다 ("오사카성"으로 검색하는 경우).
    place_match = (
        select(Place.trip_id)
        .where(Place.trip_id == Trip.id, func.lower(Place.name).like(pattern))
        .exists()
    )
    rows = db.execute(
        select(Trip, User.name)
        .join(User, Trip.user_id == User.id)
        .where(
            Trip.is_public.is_(True),
            or_(
                func.lower(Trip.title).like(pattern),
                func.lower(func.coalesce(Trip.country, "")).like(pattern),
                func.array_to_string(Trip.hashtags, ",").ilike(pattern),
                place_match,
            ),
        )
        .order_by(Trip.created_at.desc(), Trip.id)
        .limit(_SEARCH_LIMIT)
    ).all()

    return [_to_response(db, trip, owner_name, s3) for trip, owner_name in rows]


def get_public_trip(db: Session, trip_id: int) -> tuple[Trip, str]:
    """공개 여행 1건 + 소유자 이름. 비공개거나 없으면 404 (존재 여부를 흘리지 않는다)."""
    row = db.execute(
        select(Trip, User.name)
        .join(User, Trip.user_id == User.id)
        .where(Trip.id == trip_id, Trip.is_public.is_(True))
    ).first()
    if row is None:
        raise NotFoundError("공개된 여행을 찾을 수 없습니다.")
    return row[0], row[1]


def get_public_trip_detail(db: Session, s3: S3Storage, trip_id: int) -> ExploreTripDetailResponse:
    trip, owner_name = get_public_trip(db, trip_id)
    summary = _to_response(db, trip, owner_name, s3)

    places = db.scalars(
        select(Place).where(Place.trip_id == trip.id).order_by(Place.visit_order, Place.id)
    )
    detail_places = []
    for place in places:
        first_taken_at = db.scalar(
            select(func.min(Photo.taken_at)).where(Photo.place_id == place.id)
        )
        item = ExplorePlace.model_validate(place)
        item.first_taken_at = first_taken_at
        detail_places.append(item)

    return ExploreTripDetailResponse(**summary.model_dump(), places=detail_places)


def import_trip(db: Session, user: User, trip_id: int) -> Trip:
    """공개 여행을 내 여행으로 딥카피한다 (SRS 1.4.3).

    Trip·Place만 복사하고 원본의 일기·사진은 복제하지 않는다.
    아직 가보지 않은 계획이므로 is_visited는 false로 초기화한다.
    """
    source, _owner_name = get_public_trip(db, trip_id)

    copied = Trip(
        user_id=user.id,
        title=source.title,
        start_date=source.start_date,
        end_date=source.end_date,
        hashtags=list(source.hashtags),
        country=source.country,
        # 가져온 여행은 내가 다시 공개하겠다고 하기 전까지 비공개다.
        is_public=False,
    )
    db.add(copied)
    db.flush()  # id 확보

    source_places = db.scalars(
        select(Place).where(Place.trip_id == source.id).order_by(Place.visit_order, Place.id)
    )
    for order, place in enumerate(source_places, start=1):
        db.add(
            Place(
                user_id=user.id,
                trip_id=copied.id,
                name=place.name,
                anchor_lat=place.anchor_lat,
                anchor_lng=place.anchor_lng,
                radius_m=place.radius_m,
                visit_order=order,
                is_visited=False,
            )
        )

    db.commit()
    db.refresh(copied)
    return copied
