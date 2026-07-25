from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PhotoUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str

    @field_validator("content_type")
    @classmethod
    def content_type_must_be_image(cls, v: str) -> str:
        if not v.startswith("image/"):
            raise ValueError("이미지 content-type만 허용됩니다.")
        return v


class PhotoUploadResponse(BaseModel):
    photo_id: int
    s3_key: str
    upload_url: str


class PhotoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    status: str
    group_id: int | None
    latitude: float | None
    longitude: float | None
    taken_at: datetime | None
    sort_order: int | None
    # 조회 시점에 생성하는 presigned GET URL (DB에는 s3_key만 저장)
    url: str | None = None
