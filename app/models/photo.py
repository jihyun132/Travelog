from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PhotoStatus(StrEnum):
    PENDING = "PENDING"  # presign 발급됨, S3 업로드 완료 통보 전
    COMPLETED = "COMPLETED"


class Photo(Base):
    """사진 메타데이터. 파일 바이트는 S3에만 저장하고 DB에는 s3_key만 유지한다."""

    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # null = 미분류. 그룹 삭제 시 서비스에서 미분류로 되돌리며, FK는 백스톱.
    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("photo_groups.id", ondelete="SET NULL"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    s3_key: Mapped[str] = mapped_column(String(512), unique=True)
    status: Mapped[str] = mapped_column(String(20), default=PhotoStatus.PENDING)
    latitude: Mapped[float | None]
    longitude: Mapped[float | None]
    # EXIF 촬영일시는 타임존 정보가 없다 (naive datetime 그대로 저장).
    taken_at: Mapped[datetime | None] = mapped_column(DateTime())
    # 그룹 내 사용자 지정 순서. null이면 taken_at 폴백 정렬.
    sort_order: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
