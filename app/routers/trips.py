from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.diary import DiaryResponse
from app.schemas.trip import TripCreate, TripDetailResponse, TripResponse, TripUpdate
from app.services import place_service, presenters, trip_service
from app.services.s3_storage import S3Storage, get_s3_storage

router = APIRouter(prefix="/trips", tags=["trips"])


def _to_response(summary: trip_service.TripSummary, s3: S3Storage) -> TripResponse:
    response = TripResponse.model_validate(summary.trip)
    response.place_count = summary.place_count
    response.photo_count = summary.photo_count
    response.last_taken_at = summary.last_taken_at
    if summary.thumbnail is not None:
        response.thumbnail_url = s3.presign_get(summary.thumbnail.s3_key)
    return response


@router.post("", response_model=TripResponse, status_code=status.HTTP_201_CREATED)
def create_trip(
    payload: TripCreate,
    db: Session = Depends(get_db),
    s3: S3Storage = Depends(get_s3_storage),
    current_user: User = Depends(get_current_user),
) -> TripResponse:
    trip = trip_service.create_trip(db, current_user, payload)
    return _to_response(trip_service.get_trip_summary(db, trip), s3)


@router.get("", response_model=list[TripResponse])
def list_trips(
    db: Session = Depends(get_db),
    s3: S3Storage = Depends(get_s3_storage),
    current_user: User = Depends(get_current_user),
) -> list[TripResponse]:
    return [_to_response(summary, s3) for summary in trip_service.list_trips(db, current_user)]


@router.get("/{trip_id}", response_model=TripResponse)
def get_trip(
    trip_id: int,
    db: Session = Depends(get_db),
    s3: S3Storage = Depends(get_s3_storage),
    current_user: User = Depends(get_current_user),
) -> TripResponse:
    trip = trip_service.get_own_trip(db, current_user, trip_id)
    return _to_response(trip_service.get_trip_summary(db, trip), s3)


@router.get("/{trip_id}/detail", response_model=TripDetailResponse)
def get_trip_detail(
    trip_id: int,
    db: Session = Depends(get_db),
    s3: S3Storage = Depends(get_s3_storage),
    current_user: User = Depends(get_current_user),
) -> TripDetailResponse:
    """여행 상세 화면용 일괄 조회 — 방문지 + 사진 + 일기를 한 번에 반환한다.

    방문지마다 따로 호출하면 왕복이 방문지 수만큼 늘어나므로 화면 단위로 묶었다.
    """
    trip = trip_service.get_own_trip(db, current_user, trip_id)
    summary = _to_response(trip_service.get_trip_summary(db, trip), s3)

    return TripDetailResponse(
        **summary.model_dump(),
        places=[
            presenters.place_detail_response(place, place_service.list_place_photos(db, place), s3)
            for place, _count, _first_photo in place_service.list_places(db, trip)
        ],
        diaries=[
            DiaryResponse.model_validate(diary)
            for diary in trip_service.list_trip_diaries(db, trip)
        ],
    )


@router.patch("/{trip_id}", response_model=TripResponse)
def update_trip(
    trip_id: int,
    payload: TripUpdate,
    db: Session = Depends(get_db),
    s3: S3Storage = Depends(get_s3_storage),
    current_user: User = Depends(get_current_user),
) -> TripResponse:
    trip = trip_service.update_trip(db, current_user, trip_id, payload)
    return _to_response(trip_service.get_trip_summary(db, trip), s3)


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trip(
    trip_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """여행 삭제. 방문지·일기는 함께 삭제되고 사진은 미분류로 남는다."""
    trip_service.delete_trip(db, current_user, trip_id)
