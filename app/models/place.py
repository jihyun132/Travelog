from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Place(Base):
    """방문지. 대표 좌표(anchor) 반경 내의 사진이 자동 배정된다.

    경로는 별도 엔티티 없이 같은 여행 안에서 visit_order 정렬로 표현한다 (SRS 1.2.3).
    """

    __tablename__ = "places"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    anchor_lat: Mapped[float]
    anchor_lng: Mapped[float]
    # null이면 Settings.default_place_radius_m 적용
    radius_m: Mapped[int | None]
    # 여행 내 방문 순서. 생성 시 마지막 순서 다음 값으로 자동 채운다.
    visit_order: Mapped[int]
    # 마커 색상은 클라이언트가 처리한다 (SRS 1.2.1~1.2.2).
    is_visited: Mapped[bool] = mapped_column(Boolean(), server_default=text("false"))
    visited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
