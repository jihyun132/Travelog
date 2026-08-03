from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import ARRAY, Boolean, Date, DateTime, ForeignKey, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TripStatus(StrEnum):
    """여행 진행 상태. 평소에는 마지막 촬영일로 자동 판정하고,
    사용자가 직접 지정한 경우(manual_status)에만 그 값이 우선한다."""

    ON_TRIP = "ON_TRIP"
    COMPLETED = "COMPLETED"


class Trip(Base):
    """여행. 방문지(places)를 묶는 최상위 단위."""

    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(100))
    # 기간은 사진 업로드 전에는 알 수 없으므로 nullable. 둘 다 있을 때만 순서를 검증한다.
    start_date: Mapped[date | None] = mapped_column(Date())
    end_date: Mapped[date | None] = mapped_column(Date())
    hashtags: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), server_default=text("'{}'::varchar[]")
    )
    # 공개 경로 검색(P2) 대상 여부. 기본은 비공개.
    is_public: Mapped[bool] = mapped_column(Boolean(), server_default=text("false"))
    # 국가명. 서버는 지오코딩을 하지 않고(범위 외) 클라이언트가 보낸 값을 저장만 한다.
    country: Mapped[str | None] = mapped_column(String(60))
    # 여행 대표 사진. 사진이 지워져도 여행은 남아야 하므로 SET NULL.
    cover_photo_id: Mapped[int | None] = mapped_column(ForeignKey("photos.id", ondelete="SET NULL"))
    # null이면 자동 판정. 값이 있으면 TripStatus 중 하나이며 자동 판정을 덮어쓴다.
    manual_status: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
