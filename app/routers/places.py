from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.photo import Photo
from app.models.place import Place
from app.models.user import User
from app.schemas.place import (
    PhotoOrderUpdate,
    PlaceCreate,
    PlaceDetailResponse,
    PlaceOrderUpdate,
    PlaceResponse,
    PlaceUpdate,
    PlaceVisitUpdate,
)
from app.services import place_service, presenters, trip_service
from app.services.s3_storage import S3Storage, get_s3_storage

# 여행에 종속된 경로 (생성·목록·순서)
trip_places_router = APIRouter(prefix="/trips/{trip_id}/places", tags=["places"])
# 방문지 단건 경로 — 여행 id 없이 접근한다
router = APIRouter(prefix="/places", tags=["places"])


def _to_summary(
    db: Session, place: Place, count: int, first_photo: Photo | None, s3: S3Storage
) -> PlaceResponse:
    return presenters.place_response(
        place,
        s3,
        photo_count=count,
        first_photo=first_photo,
        first_taken_at=place_service.first_taken_at(db, place),
    )


# ── 여행 종속 경로 ────────────────────────────────────────


@trip_places_router.post("", response_model=PlaceResponse, status_code=status.HTTP_201_CREATED)
def create_place(
    trip_id: int,
    payload: PlaceCreate,
    db: Session = Depends(get_db),
    s3: S3Storage = Depends(get_s3_storage),
    current_user: User = Depends(get_current_user),
) -> PlaceResponse:
    """방문지 생성. 생성 즉시 반경 내 미분류 사진을 편입한다."""
    trip = trip_service.get_own_trip(db, current_user, trip_id)
    place = place_service.create_place(db, current_user, trip, payload)
    photos = place_service.list_place_photos(db, place)
    return _to_summary(db, place, len(photos), photos[0] if photos else None, s3)


@trip_places_router.get("", response_model=list[PlaceResponse])
def list_places(
    trip_id: int,
    db: Session = Depends(get_db),
    s3: S3Storage = Depends(get_s3_storage),
    current_user: User = Depends(get_current_user),
) -> list[PlaceResponse]:
    """여행의 방문지 목록. 경로 순서(visit_order)로 정렬된다."""
    trip = trip_service.get_own_trip(db, current_user, trip_id)
    return [
        _to_summary(db, place, count, first_photo, s3)
        for place, count, first_photo in place_service.list_places(db, trip)
    ]


@trip_places_router.put("/order", response_model=list[PlaceResponse])
def reorder_places(
    trip_id: int,
    payload: PlaceOrderUpdate,
    db: Session = Depends(get_db),
    s3: S3Storage = Depends(get_s3_storage),
    current_user: User = Depends(get_current_user),
) -> list[PlaceResponse]:
    """경로 재정렬 (SRS 1.2.3). 전체 방문지 ID 배열을 순서대로 받는다."""
    trip = trip_service.get_own_trip(db, current_user, trip_id)
    place_service.reorder_places(db, trip, payload.place_ids)
    return [
        _to_summary(db, place, count, first_photo, s3)
        for place, count, first_photo in place_service.list_places(db, trip)
    ]


# ── 방문지 단건 경로 ──────────────────────────────────────


@router.get("/{place_id}", response_model=PlaceDetailResponse)
def get_place(
    place_id: int,
    db: Session = Depends(get_db),
    s3: S3Storage = Depends(get_s3_storage),
    current_user: User = Depends(get_current_user),
) -> PlaceDetailResponse:
    """방문지 상세: 사진 목록을 사용자 지정 순서(sort_order → 촬영일시)로 반환."""
    place = place_service.get_own_place(db, current_user, place_id)
    return presenters.place_detail_response(place, place_service.list_place_photos(db, place), s3)


@router.patch("/{place_id}", response_model=PlaceResponse)
def update_place(
    place_id: int,
    payload: PlaceUpdate,
    db: Session = Depends(get_db),
    s3: S3Storage = Depends(get_s3_storage),
    current_user: User = Depends(get_current_user),
) -> PlaceResponse:
    """이름/대표 좌표/반경 수정. 좌표·반경 변경 시 소속 사진을 재배정한다."""
    place = place_service.update_place(db, current_user, place_id, payload)
    photos = place_service.list_place_photos(db, place)
    return _to_summary(db, place, len(photos), photos[0] if photos else None, s3)


@router.patch("/{place_id}/visit", response_model=PlaceResponse)
def set_visited(
    place_id: int,
    payload: PlaceVisitUpdate,
    db: Session = Depends(get_db),
    s3: S3Storage = Depends(get_s3_storage),
    current_user: User = Depends(get_current_user),
) -> PlaceResponse:
    """방문 처리 (SRS 1.2.4). 마커 색상은 응답의 is_visited로 클라이언트가 판단한다."""
    place = place_service.set_visited(db, current_user, place_id, payload.is_visited)
    photos = place_service.list_place_photos(db, place)
    return _to_summary(db, place, len(photos), photos[0] if photos else None, s3)


@router.delete("/{place_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_place(
    place_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """방문지 삭제. 소속 사진은 삭제하지 않고 미분류로 되돌린다."""
    place_service.delete_place(db, current_user, place_id)


@router.put("/{place_id}/photos/order", response_model=PlaceDetailResponse)
def update_photo_order(
    place_id: int,
    payload: PhotoOrderUpdate,
    db: Session = Depends(get_db),
    s3: S3Storage = Depends(get_s3_storage),
    current_user: User = Depends(get_current_user),
) -> PlaceDetailResponse:
    """사용자가 조정한 사진 순서(전체 ID 배열)를 저장하고 반영된 목록을 반환."""
    photos = place_service.update_photo_order(db, current_user, place_id, payload.photo_ids)
    place = place_service.get_own_place(db, current_user, place_id)
    return presenters.place_detail_response(place, photos, s3)
