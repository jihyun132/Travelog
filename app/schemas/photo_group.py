from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.photo import PhotoResponse


class PhotoGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    anchor_lat: float = Field(ge=-90, le=90)
    anchor_lng: float = Field(ge=-180, le=180)
    radius_m: int | None = Field(default=None, ge=1, le=1000)


class PhotoGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    anchor_lat: float | None = Field(default=None, ge=-90, le=90)
    anchor_lng: float | None = Field(default=None, ge=-180, le=180)
    radius_m: int | None = Field(default=None, ge=1, le=1000)


class PhotoGroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    anchor_lat: float
    anchor_lng: float
    radius_m: int | None
    created_at: datetime
    photo_count: int = 0
    thumbnail_url: str | None = None


class PhotoGroupDetailResponse(PhotoGroupResponse):
    photos: list[PhotoResponse] = []


class PhotoOrderUpdate(BaseModel):
    photo_ids: list[int] = Field(min_length=1)
