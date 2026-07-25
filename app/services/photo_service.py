import uuid
from datetime import datetime
from io import BytesIO

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import InvalidPhotoError, NotFoundError
from app.models.photo import Photo, PhotoStatus
from app.models.user import User
from app.schemas.photo import PhotoResponse
from app.services.photo_group_service import find_group_in_radius
from app.services.s3_storage import S3Storage

_GPS_IFD = 0x8825
_EXIF_IFD = 0x8769
_TAG_DATETIME_ORIGINAL = 0x9003

_TAG_LAT_REF = 1
_TAG_LAT = 2
_TAG_LNG_REF = 3
_TAG_LNG = 4


def _dms_to_decimal(dms, ref: str) -> float:
    degrees, minutes, seconds = (float(v) for v in dms)
    decimal = degrees + minutes / 60 + seconds / 3600
    return -decimal if ref in ("S", "W") else decimal


def extract_exif(data: bytes) -> tuple[float | None, float | None, datetime | None]:
    """이미지 바이트에서 (위도, 경도, 촬영일시)를 추출한다.

    GPS·촬영일시가 없으면 해당 값은 None (미분류 사진으로 저장).
    이미지 파일이 아니면 InvalidPhotoError.
    """
    try:
        image = Image.open(BytesIO(data))
    except UnidentifiedImageError:
        raise InvalidPhotoError("이미지 파일이 아닙니다.") from None

    exif = image.getexif()
    gps = exif.get_ifd(_GPS_IFD)
    lat_dms, lat_ref = gps.get(_TAG_LAT), gps.get(_TAG_LAT_REF)
    lng_dms, lng_ref = gps.get(_TAG_LNG), gps.get(_TAG_LNG_REF)

    latitude = longitude = None
    if lat_dms and lat_ref and lng_dms and lng_ref:
        latitude = _dms_to_decimal(lat_dms, lat_ref)
        longitude = _dms_to_decimal(lng_dms, lng_ref)

    taken_at: datetime | None = None
    raw_taken = exif.get_ifd(_EXIF_IFD).get(_TAG_DATETIME_ORIGINAL)
    if raw_taken:
        try:
            taken_at = datetime.strptime(raw_taken, "%Y:%m:%d %H:%M:%S")
        except ValueError:
            taken_at = None

    return latitude, longitude, taken_at


def create_upload(
    db: Session, s3: S3Storage, user: User, filename: str, content_type: str
) -> tuple[Photo, str]:
    """presigned PUT URL을 발급하고 PENDING 사진 행을 만든다."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    s3_key = f"users/{user.id}/photos/{uuid.uuid4().hex}.{ext}"
    photo = Photo(user_id=user.id, filename=filename, s3_key=s3_key, status=PhotoStatus.PENDING)
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return photo, s3.presign_put(s3_key, content_type)


def get_own_photo(db: Session, user: User, photo_id: int) -> Photo:
    photo = db.get(Photo, photo_id)
    if photo is None or photo.user_id != user.id:
        raise NotFoundError("사진을 찾을 수 없습니다.")
    return photo


def complete_upload(db: Session, s3: S3Storage, user: User, photo_id: int) -> Photo:
    """S3 업로드 완료 통보: EXIF 추출 → 좌표 저장 → 반경 내 그룹 자동 배정."""
    photo = get_own_photo(db, user, photo_id)
    try:
        data = s3.get_object(photo.s3_key)
    except FileNotFoundError:
        raise InvalidPhotoError(
            "업로드된 파일을 찾을 수 없습니다. S3 업로드를 먼저 완료해주세요."
        ) from None

    latitude, longitude, taken_at = extract_exif(data)
    photo.latitude = latitude
    photo.longitude = longitude
    photo.taken_at = taken_at
    photo.status = PhotoStatus.COMPLETED

    group = None
    if latitude is not None and longitude is not None:
        group = find_group_in_radius(db, user.id, latitude, longitude)
    photo.group_id = group.id if group else None
    photo.sort_order = None

    db.commit()
    db.refresh(photo)
    return photo


def list_unassigned(db: Session, user: User) -> list[Photo]:
    """어느 그룹에도 속하지 않은(미분류) 완료 사진 목록."""
    return list(
        db.scalars(
            select(Photo)
            .where(
                Photo.user_id == user.id,
                Photo.group_id.is_(None),
                Photo.status == PhotoStatus.COMPLETED,
            )
            .order_by(Photo.taken_at.asc().nulls_last(), Photo.id)
        )
    )


def to_response(photo: Photo, s3: S3Storage) -> PhotoResponse:
    """presigned GET URL을 붙인 응답 스키마로 변환한다."""
    response = PhotoResponse.model_validate(photo)
    if photo.status == PhotoStatus.COMPLETED:
        response.url = s3.presign_get(photo.s3_key)
    return response
