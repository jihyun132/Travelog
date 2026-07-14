from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PhotoLocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    latitude: float
    longitude: float
    taken_at: datetime | None
