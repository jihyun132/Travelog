"""add trips and promote photo_groups to places

Revision ID: b7f3a91c2e64
Revises: 60d56ee79361
Create Date: 2026-07-25 12:10:00.000000

photo_groups(사진 그룹)를 places(방문지)로 승격하고 상위 단위인 trips(여행)를 추가한다.
기존 방문지는 사용자별 기본 여행 1건으로 묶어 백필한다.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7f3a91c2e64"
down_revision: str | None = "60d56ee79361"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── trips ────────────────────────────────────────────
    op.create_table(
        "trips",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column(
            "hashtags",
            sa.ARRAY(sa.String(length=50)),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column("is_public", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_trips_user_id"), "trips", ["user_id"], unique=False)

    # ── photo_groups → places ────────────────────────────
    op.rename_table("photo_groups", "places")
    op.execute("ALTER SEQUENCE photo_groups_id_seq RENAME TO places_id_seq")
    op.execute("ALTER INDEX ix_photo_groups_user_id RENAME TO ix_places_user_id")
    op.execute("ALTER TABLE places RENAME CONSTRAINT photo_groups_pkey TO places_pkey")
    op.execute(
        "ALTER TABLE places RENAME CONSTRAINT photo_groups_user_id_fkey TO places_user_id_fkey"
    )

    # 백필이 끝날 때까지 nullable로 둔다.
    op.add_column("places", sa.Column("trip_id", sa.Integer(), nullable=True))
    op.add_column("places", sa.Column("visit_order", sa.Integer(), nullable=True))
    op.add_column(
        "places",
        sa.Column("is_visited", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("places", sa.Column("visited_at", sa.DateTime(timezone=True), nullable=True))

    # 기존 방문지를 사용자별 기본 여행 1건으로 묶는다 (hashtags·is_public·created_at은 서버 기본값).
    op.execute("INSERT INTO trips (user_id, title) SELECT DISTINCT user_id, '내 여행' FROM places")
    op.execute(
        "UPDATE places p SET trip_id = t.id FROM trips t "
        "WHERE t.user_id = p.user_id AND p.trip_id IS NULL"
    )
    op.execute(
        "UPDATE places p SET visit_order = sub.rn FROM ("
        "SELECT id, row_number() OVER (PARTITION BY trip_id ORDER BY id) AS rn FROM places"
        ") sub WHERE p.id = sub.id"
    )

    op.alter_column("places", "trip_id", nullable=False)
    op.alter_column("places", "visit_order", nullable=False)
    op.create_foreign_key(
        "places_trip_id_fkey", "places", "trips", ["trip_id"], ["id"], ondelete="CASCADE"
    )
    op.create_index(op.f("ix_places_trip_id"), "places", ["trip_id"], unique=False)

    # ── photos.group_id → place_id ───────────────────────
    op.alter_column("photos", "group_id", new_column_name="place_id")
    op.execute("ALTER INDEX ix_photos_group_id RENAME TO ix_photos_place_id")
    op.execute("ALTER TABLE photos RENAME CONSTRAINT photos_group_id_fkey TO photos_place_id_fkey")

    # ── diaries.group_id → place_id ──────────────────────
    op.alter_column("diaries", "group_id", new_column_name="place_id")
    op.execute(
        "ALTER TABLE diaries RENAME CONSTRAINT diaries_group_id_fkey TO diaries_place_id_fkey"
    )
    op.execute("ALTER TABLE diaries RENAME CONSTRAINT diaries_group_id_key TO diaries_place_id_key")


def downgrade() -> None:
    op.execute("ALTER TABLE diaries RENAME CONSTRAINT diaries_place_id_key TO diaries_group_id_key")
    op.execute(
        "ALTER TABLE diaries RENAME CONSTRAINT diaries_place_id_fkey TO diaries_group_id_fkey"
    )
    op.alter_column("diaries", "place_id", new_column_name="group_id")

    op.execute("ALTER TABLE photos RENAME CONSTRAINT photos_place_id_fkey TO photos_group_id_fkey")
    op.execute("ALTER INDEX ix_photos_place_id RENAME TO ix_photos_group_id")
    op.alter_column("photos", "place_id", new_column_name="group_id")

    op.drop_index(op.f("ix_places_trip_id"), table_name="places")
    op.drop_constraint("places_trip_id_fkey", "places", type_="foreignkey")
    op.drop_column("places", "visited_at")
    op.drop_column("places", "is_visited")
    op.drop_column("places", "visit_order")
    op.drop_column("places", "trip_id")

    op.execute(
        "ALTER TABLE places RENAME CONSTRAINT places_user_id_fkey TO photo_groups_user_id_fkey"
    )
    op.execute("ALTER TABLE places RENAME CONSTRAINT places_pkey TO photo_groups_pkey")
    op.execute("ALTER INDEX ix_places_user_id RENAME TO ix_photo_groups_user_id")
    op.execute("ALTER SEQUENCE places_id_seq RENAME TO photo_groups_id_seq")
    op.rename_table("places", "photo_groups")

    op.drop_index(op.f("ix_trips_user_id"), table_name="trips")
    op.drop_table("trips")
