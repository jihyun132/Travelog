"""add trip country, cover_photo_id, manual_status

Revision ID: c1a4d7e93b52
Revises: b7f3a91c2e64
Create Date: 2026-08-03 10:00:00.000000

프론트에 이미 있는 국기 표시·대표사진 변경·여행 상태 변경 UI가 저장할 곳을 만든다.
셋 다 nullable이라 기존 데이터에는 영향이 없다.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1a4d7e93b52"
down_revision: str | None = "b7f3a91c2e64"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("country", sa.String(length=60), nullable=True))
    op.add_column("trips", sa.Column("cover_photo_id", sa.Integer(), nullable=True))
    op.add_column("trips", sa.Column("manual_status", sa.String(length=20), nullable=True))
    # 사진이 삭제돼도 여행은 남아야 하므로 SET NULL.
    op.create_foreign_key(
        "trips_cover_photo_id_fkey",
        "trips",
        "photos",
        ["cover_photo_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("trips_cover_photo_id_fkey", "trips", type_="foreignkey")
    op.drop_column("trips", "manual_status")
    op.drop_column("trips", "cover_photo_id")
    op.drop_column("trips", "country")
