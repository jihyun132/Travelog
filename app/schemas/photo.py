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


class PhotoCompleteRequest(BaseModel):
    """업로드 완료 통보. place_id를 주면 반경 자동 배정 대신 그 방문지로 확정 배정한다.

    클라이언트가 이미 사진을 방문지로 묶어둔 경우(업로드 플로우) 필요하다.
    자동 배정은 사용자의 '모든' 방문지를 대상으로 하므로, 재방문 지역에서는
    새 여행 사진이 과거 여행의 방문지로 흡수될 수 있다.
    """

    place_id: int | None = None


class PhotoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    status: str
    place_id: int | None
    latitude: float | None
    longitude: float | None
    taken_at: datetime | None
    sort_order: int | None
    # 조회 시점에 생성하는 presigned GET URL (DB에는 s3_key만 저장)
    url: str | None = None
