from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PhotoGroup(Base):
    """사용자가 직접 만드는 사진 그룹(대표 여행지). anchor 반경 내 사진이 자동 배정된다."""

    __tablename__ = "photo_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    anchor_lat: Mapped[float]
    anchor_lng: Mapped[float]
    # null이면 Settings.default_group_radius_m 적용
    radius_m: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
