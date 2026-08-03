from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.trip import TripStatus
from app.schemas.diary import DiaryResponse
from app.schemas.place import PlaceDetailResponse


class TripCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    start_date: date | None = None
    end_date: date | None = None
    hashtags: list[str] = Field(default_factory=list, max_length=20)
    is_public: bool = False
    # 서버는 지오코딩을 하지 않는다 (범위 외). 클라이언트가 역지오코딩한 값을 저장만 한다.
    country: str | None = Field(default=None, max_length=60)

    @model_validator(mode="after")
    def end_date_must_not_precede_start(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("종료일은 시작일보다 빠를 수 없습니다.")
        return self


class TripUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    start_date: date | None = None
    end_date: date | None = None
    hashtags: list[str] | None = Field(default=None, max_length=20)
    is_public: bool | None = None
    country: str | None = Field(default=None, max_length=60)
    cover_photo_id: int | None = None
    # null을 명시하면 수동 지정을 해제하고 자동 판정으로 되돌린다.
    manual_status: TripStatus | None = None


class TripResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    start_date: date | None
    end_date: date | None
    hashtags: list[str]
    is_public: bool
    country: str | None
    cover_photo_id: int | None
    manual_status: TripStatus | None
    created_at: datetime
    place_count: int = 0
    photo_count: int = 0
    # 상태 자동 판정 기준값. 클라이언트가 사진을 전부 받지 않고도 ON_TRIP 여부를 계산한다.
    last_taken_at: datetime | None = None
    thumbnail_url: str | None = None


class TripDetailResponse(TripResponse):
    """여행 상세 일괄 조회 — 화면 하나가 필요한 방문지·사진·일기를 한 번에 담는다."""

    places: list[PlaceDetailResponse] = []
    diaries: list[DiaryResponse] = []
