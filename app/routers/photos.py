from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.photo import (
    PhotoCompleteRequest,
    PhotoResponse,
    PhotoUploadRequest,
    PhotoUploadResponse,
)
from app.services import photo_service, presenters
from app.services.s3_storage import S3Storage, get_s3_storage

router = APIRouter(prefix="/photos", tags=["photos"])


@router.post("/presign", response_model=PhotoUploadResponse, status_code=status.HTTP_201_CREATED)
def presign_upload(
    payload: PhotoUploadRequest,
    db: Session = Depends(get_db),
    s3: S3Storage = Depends(get_s3_storage),
    current_user: User = Depends(get_current_user),
) -> PhotoUploadResponse:
    """S3 직접 업로드용 presigned PUT URL 발급. 파일은 서버를 거치지 않는다."""
    photo, upload_url = photo_service.create_upload(
        db, s3, current_user, payload.filename, payload.content_type
    )
    return PhotoUploadResponse(photo_id=photo.id, s3_key=photo.s3_key, upload_url=upload_url)


@router.post("/{photo_id}/complete", response_model=PhotoResponse)
def complete_upload(
    photo_id: int,
    payload: PhotoCompleteRequest | None = None,
    db: Session = Depends(get_db),
    s3: S3Storage = Depends(get_s3_storage),
    current_user: User = Depends(get_current_user),
) -> PhotoResponse:
    """업로드 완료 통보: EXIF(GPS·촬영일시) 추출 후 방문지에 배정.

    본문에 place_id를 주면 그 방문지로 확정 배정하고, 없으면 반경 내 방문지를 자동 탐색한다.
    """
    photo = photo_service.complete_upload(
        db, s3, current_user, photo_id, place_id=payload.place_id if payload else None
    )
    return presenters.photo_response(photo, s3)


@router.get("/unassigned", response_model=list[PhotoResponse])
def list_unassigned(
    db: Session = Depends(get_db),
    s3: S3Storage = Depends(get_s3_storage),
    current_user: User = Depends(get_current_user),
) -> list[PhotoResponse]:
    """어느 방문지에도 속하지 않은 미분류 사진 목록."""
    photos = photo_service.list_unassigned(db, current_user)
    return [presenters.photo_response(photo, s3) for photo in photos]
