from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.photo import PhotoResponse


class PlaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    anchor_lat: float = Field(ge=-90, le=90)
    anchor_lng: float = Field(ge=-180, le=180)
    radius_m: int | None = Field(default=None, ge=1, le=1000)


class PlaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    anchor_lat: float | None = Field(default=None, ge=-90, le=90)
    anchor_lng: float | None = Field(default=None, ge=-180, le=180)
    radius_m: int | None = Field(default=None, ge=1, le=1000)


class PlaceVisitUpdate(BaseModel):
    is_visited: bool


class PlaceOrderUpdate(BaseModel):
    """여행 내 방문 순서 재정렬 (전체 방문지 ID 배열)."""

    place_ids: list[int] = Field(min_length=1)


class PlaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trip_id: int
    name: str
    anchor_lat: float
    anchor_lng: float
    radius_m: int | None
    visit_order: int
    is_visited: bool
    visited_at: datetime | None
    created_at: datetime
    photo_count: int = 0
    # 이 방문지의 첫 촬영 시각. 클라이언트가 방문 시각 라벨을 만드는 데 쓴다.
    first_taken_at: datetime | None = None
    thumbnail_url: str | None = None


class PlaceDetailResponse(PlaceResponse):
    photos: list[PhotoResponse] = []


class PhotoOrderUpdate(BaseModel):
    photo_ids: list[int] = Field(min_length=1)
