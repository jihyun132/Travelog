from datetime import datetime
from io import BytesIO

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import InvalidPhotoError
from app.models.photo_location import PhotoLocation
from app.models.user import User

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


def extract_gps(data: bytes) -> tuple[float, float, datetime | None]:
    """이미지 바이트에서 (위도, 경도, 촬영일시)를 추출한다. GPS가 없으면 InvalidPhotoError."""
    try:
        image = Image.open(BytesIO(data))
    except UnidentifiedImageError:
        raise InvalidPhotoError("이미지 파일이 아닙니다.") from None

    exif = image.getexif()
    gps = exif.get_ifd(_GPS_IFD)
    lat_dms, lat_ref = gps.get(_TAG_LAT), gps.get(_TAG_LAT_REF)
    lng_dms, lng_ref = gps.get(_TAG_LNG), gps.get(_TAG_LNG_REF)
    if not lat_dms or not lat_ref or not lng_dms or not lng_ref:
        raise InvalidPhotoError("사진에 GPS 정보가 없습니다.")

    taken_at: datetime | None = None
    raw_taken = exif.get_ifd(_EXIF_IFD).get(_TAG_DATETIME_ORIGINAL)
    if raw_taken:
        try:
            taken_at = datetime.strptime(raw_taken, "%Y:%m:%d %H:%M:%S")
        except ValueError:
            taken_at = None

    return (
        _dms_to_decimal(lat_dms, lat_ref),
        _dms_to_decimal(lng_dms, lng_ref),
        taken_at,
    )


def create_photo_location(
    db: Session, user: User, filename: str | None, data: bytes
) -> PhotoLocation:
    latitude, longitude, taken_at = extract_gps(data)
    location = PhotoLocation(
        user_id=user.id,
        filename=filename or "unknown",
        latitude=latitude,
        longitude=longitude,
        taken_at=taken_at,
    )
    db.add(location)
    db.commit()
    db.refresh(location)
    return location


def list_photo_locations(db: Session, user: User) -> list[PhotoLocation]:
    return list(
        db.scalars(
            select(PhotoLocation).where(PhotoLocation.user_id == user.id).order_by(PhotoLocation.id)
        )
    )
