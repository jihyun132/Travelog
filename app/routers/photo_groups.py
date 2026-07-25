from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.photo import Photo
from app.models.photo_group import PhotoGroup
from app.models.user import User
from app.schemas.photo_group import (
    PhotoGroupCreate,
    PhotoGroupDetailResponse,
    PhotoGroupResponse,
    PhotoGroupUpdate,
    PhotoOrderUpdate,
)
from app.services import photo_group_service, photo_service
from app.services.s3_storage import S3Storage, get_s3_storage

router = APIRouter(prefix="/photo-groups", tags=["photo-groups"])


def _to_summary(
    group: PhotoGroup, count: int, first_photo: Photo | None, s3: S3Storage
) -> PhotoGroupResponse:
    response = PhotoGroupResponse.model_validate(group)
    response.photo_count = count
    if first_photo is not None:
        response.thumbnail_url = s3.presign_get(first_photo.s3_key)
    return response


@router.post("", response_model=PhotoGroupResponse, status_code=status.HTTP_201_CREATED)
def create_group(
    payload: PhotoGroupCreate,
    db: Session = Depends(get_db),
    s3: S3Storage = Depends(get_s3_storage),
    current_user: User = Depends(get_current_user),
) -> PhotoGroupResponse:
    """그룹(대표 여행지) 생성. 생성 즉시 반경 내 미분류 사진을 편입한다."""
    group = photo_group_service.create_group(db, current_user, payload)
    photos = photo_group_service.list_group_photos(db, group)
    return _to_summary(group, len(photos), photos[0] if photos else None, s3)


@router.get("", response_model=list[PhotoGroupResponse])
def list_groups(
    db: Session = Depends(get_db),
    s3: S3Storage = Depends(get_s3_storage),
    current_user: User = Depends(get_current_user),
) -> list[PhotoGroupResponse]:
    return [
        _to_summary(group, count, first_photo, s3)
        for group, count, first_photo in photo_group_service.list_groups(db, current_user)
    ]


@router.get("/{group_id}", response_model=PhotoGroupDetailResponse)
def get_group(
    group_id: int,
    db: Session = Depends(get_db),
    s3: S3Storage = Depends(get_s3_storage),
    current_user: User = Depends(get_current_user),
) -> PhotoGroupDetailResponse:
    """그룹 상세: 사진 목록을 사용자 지정 순서(sort_order → 촬영일시)로 반환."""
    group = photo_group_service.get_own_group(db, current_user, group_id)
    photos = photo_group_service.list_group_photos(db, group)
    response = PhotoGroupDetailResponse.model_validate(group)
    response.photo_count = len(photos)
    response.photos = [photo_service.to_response(photo, s3) for photo in photos]
    return response


@router.patch("/{group_id}", response_model=PhotoGroupResponse)
def update_group(
    group_id: int,
    payload: PhotoGroupUpdate,
    db: Session = Depends(get_db),
    s3: S3Storage = Depends(get_s3_storage),
    current_user: User = Depends(get_current_user),
) -> PhotoGroupResponse:
    """이름/대표 좌표/반경 수정. 좌표·반경 변경 시 소속 사진을 재배정한다."""
    group = photo_group_service.update_group(db, current_user, group_id, payload)
    photos = photo_group_service.list_group_photos(db, group)
    return _to_summary(group, len(photos), photos[0] if photos else None, s3)


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """그룹 삭제. 소속 사진은 삭제하지 않고 미분류로 되돌린다."""
    photo_group_service.delete_group(db, current_user, group_id)


@router.put("/{group_id}/photos/order", response_model=PhotoGroupDetailResponse)
def update_photo_order(
    group_id: int,
    payload: PhotoOrderUpdate,
    db: Session = Depends(get_db),
    s3: S3Storage = Depends(get_s3_storage),
    current_user: User = Depends(get_current_user),
) -> PhotoGroupDetailResponse:
    """사용자가 조정한 사진 순서(전체 ID 배열)를 저장하고 반영된 목록을 반환."""
    photos = photo_group_service.update_photo_order(db, current_user, group_id, payload.photo_ids)
    group = photo_group_service.get_own_group(db, current_user, group_id)
    response = PhotoGroupDetailResponse.model_validate(group)
    response.photo_count = len(photos)
    response.photos = [photo_service.to_response(photo, s3) for photo in photos]
    return response
