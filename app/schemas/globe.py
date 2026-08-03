from datetime import date

from pydantic import BaseModel, ConfigDict


class GlobePlace(BaseModel):
    """지구본 마커 1개. 색상 구분은 is_visited로 클라이언트가 처리한다 (SRS 1.2.1~1.2.2)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    anchor_lat: float
    anchor_lng: float
    visit_order: int
    is_visited: bool


class GlobeTrip(BaseModel):
    """여행 1건 + 그 경로. places는 visit_order 순이므로 그대로 이어 그리면 경로가 된다."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    start_date: date | None
    end_date: date | None
    places: list[GlobePlace] = []


class GlobeResponse(BaseModel):
    trips: list[GlobeTrip] = []
