from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.diary import Weather


class DiaryUpsert(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    weather: Weather | None = None


class DiaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: int
    content: str
    weather: Weather | None
    created_at: datetime
    updated_at: datetime
