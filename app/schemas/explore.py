from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ExplorePlace(BaseModel):
    """공개 여행의 방문지. 가져오기(딥카피) 대상이므로 좌표를 포함한다."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    anchor_lat: float
    anchor_lng: float
    visit_order: int
    first_taken_at: datetime | None = None


class ExploreTripResponse(BaseModel):
    """검색 결과 카드. 남의 여행이므로 일기·사진 원본은 노출하지 않는다."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    country: str | None
    start_date: date | None
    end_date: date | None
    hashtags: list[str]
    owner_name: str
    place_count: int = 0
    # 기간이 없으면 null. 클라이언트가 "N일" 표기를 만들 때 쓴다.
    duration_days: int | None = None
    thumbnail_url: str | None = None


class ExploreTripDetailResponse(ExploreTripResponse):
    places: list[ExplorePlace] = []
