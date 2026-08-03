from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.diary import Weather


class DiaryUpsert(BaseModel):
    # 날씨만 기록하고 본문은 비워두는 저장을 허용한다 (프론트 일기 화면이 이를 허용한다).
    content: str = Field(default="", max_length=10000)
    weather: Weather | None = None


class DiaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    place_id: int
    content: str
    weather: Weather | None
    created_at: datetime
    updated_at: datetime
