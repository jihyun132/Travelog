from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PhotoLocation(Base):
    """EXIF 좌표 파싱 검증용 임시 엔티티. 사진 파일 자체는 어디에도 저장하지 않는다."""

    __tablename__ = "photo_locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    latitude: Mapped[float]
    longitude: Mapped[float]
    # EXIF 촬영일시는 타임존 정보가 없다 (naive datetime 그대로 저장).
    taken_at: Mapped[datetime | None] = mapped_column(DateTime())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
