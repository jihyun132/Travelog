from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.explore import ExploreTripDetailResponse, ExploreTripResponse
from app.schemas.trip import TripResponse
from app.services import explore_service, trip_service
from app.services.s3_storage import S3Storage, get_s3_storage

router = APIRouter(prefix="/explore", tags=["explore"])


@router.get("/trips", response_model=list[ExploreTripResponse])
def search_public_trips(
    q: str = Query(default="", max_length=100, description="제목·국가·해시태그·방문지명"),
    db: Session = Depends(get_db),
    s3: S3Storage = Depends(get_s3_storage),
) -> list[ExploreTripResponse]:
    """공개 여행 검색 (SRS 1.4.1). 게스트도 조회할 수 있다 (SRS 0.3.2)."""
    return explore_service.search_trips(db, s3, q)


@router.get("/trips/{trip_id}", response_model=ExploreTripDetailResponse)
def get_public_trip(
    trip_id: int,
    db: Session = Depends(get_db),
    s3: S3Storage = Depends(get_s3_storage),
) -> ExploreTripDetailResponse:
    """공개 여행 상세 — 경로(방문지 목록)까지. 원본의 일기·사진은 노출하지 않는다."""
    return explore_service.get_public_trip_detail(db, s3, trip_id)


@router.post(
    "/trips/{trip_id}/import", response_model=TripResponse, status_code=status.HTTP_201_CREATED
)
def import_public_trip(
    trip_id: int,
    db: Session = Depends(get_db),
    s3: S3Storage = Depends(get_s3_storage),
    current_user: User = Depends(get_current_user),
) -> TripResponse:
    """공개 경로를 내 여행으로 가져온다 (SRS 1.4.3). 게스트는 401."""
    trip = explore_service.import_trip(db, current_user, trip_id)
    summary = trip_service.get_trip_summary(db, trip)

    response = TripResponse.model_validate(summary.trip)
    response.place_count = summary.place_count
    response.photo_count = summary.photo_count
    response.last_taken_at = summary.last_taken_at
    return response
