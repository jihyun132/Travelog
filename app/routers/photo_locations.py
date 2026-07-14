from fastapi import APIRouter, Depends, UploadFile, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.photo_location import PhotoLocationResponse
from app.services import photo_location_service

router = APIRouter(prefix="/photo-locations", tags=["photo-locations"])


@router.post("", response_model=PhotoLocationResponse, status_code=status.HTTP_201_CREATED)
def upload_photo_location(
    file: UploadFile,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PhotoLocationResponse:
    """사진에서 EXIF 좌표를 파싱해 저장한다. 파일 자체는 저장하지 않는다."""
    data = file.file.read()
    location = photo_location_service.create_photo_location(db, current_user, file.filename, data)
    return PhotoLocationResponse.model_validate(location)


@router.get("", response_model=list[PhotoLocationResponse])
def list_photo_locations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[PhotoLocationResponse]:
    locations = photo_location_service.list_photo_locations(db, current_user)
    return [PhotoLocationResponse.model_validate(loc) for loc in locations]
