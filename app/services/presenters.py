"""SQLAlchemy 모델 → 응답 스키마 변환.

여러 라우터가 같은 모델을 응답으로 내보내므로 변환을 한곳에 모았다.
서비스 계층을 import하지 않아 photo_service ↔ place_service 순환을 피한다.
"""

from datetime import datetime

from app.models.photo import Photo, PhotoStatus
from app.models.place import Place
from app.schemas.photo import PhotoResponse
from app.schemas.place import PlaceDetailResponse, PlaceResponse
from app.services.s3_storage import S3Storage


def photo_response(photo: Photo, s3: S3Storage) -> PhotoResponse:
    """presigned GET URL을 붙인 사진 응답. 업로드 완료 전에는 URL이 없다."""
    response = PhotoResponse.model_validate(photo)
    if photo.status == PhotoStatus.COMPLETED:
        response.url = s3.presign_get(photo.s3_key)
    return response


def place_response(
    place: Place,
    s3: S3Storage,
    *,
    photo_count: int,
    first_photo: Photo | None,
    first_taken_at: datetime | None = None,
) -> PlaceResponse:
    """방문지 요약 (목록·카드용). 사진 자체는 싣지 않는다."""
    response = PlaceResponse.model_validate(place)
    response.photo_count = photo_count
    response.first_taken_at = first_taken_at if first_taken_at else None
    if first_photo is not None:
        response.thumbnail_url = s3.presign_get(first_photo.s3_key)
    return response


def place_detail_response(place: Place, photos: list[Photo], s3: S3Storage) -> PlaceDetailResponse:
    """방문지 상세 — 사진 목록 포함. 촬영 시각은 실린 사진에서 그대로 계산한다."""
    response = PlaceDetailResponse.model_validate(place)
    response.photo_count = len(photos)
    response.photos = [photo_response(photo, s3) for photo in photos]
    taken = [photo.taken_at for photo in photos if photo.taken_at is not None]
    response.first_taken_at = min(taken) if taken else None
    if photos:
        response.thumbnail_url = s3.presign_get(photos[0].s3_key)
    return response
