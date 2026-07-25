from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Weather(StrEnum):
    SUNNY = "SUNNY"
    CLOUDY = "CLOUDY"
    RAINY = "RAINY"
    SNOWY = "SNOWY"


class Diary(Base):
    """방문지(사진 그룹) 단위 일기. 그룹당 1개만 존재한다."""

    __tablename__ = "diaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # 그룹 삭제 시 일기도 함께 삭제된다 (사진과 달리 그룹 밖에서는 접근 경로가 없다).
    group_id: Mapped[int] = mapped_column(
        ForeignKey("photo_groups.id", ondelete="CASCADE"), unique=True
    )
    content: Mapped[str] = mapped_column(Text())
    weather: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
