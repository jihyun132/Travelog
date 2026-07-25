import os

# app 모듈 import 전에 테스트 DB로 강제 전환한다 (.env보다 환경변수가 우선).
TEST_DATABASE_URL = "postgresql+psycopg://travelog:travelog@localhost:5432/travelog_test"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import psycopg  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402


def _ensure_test_database() -> None:
    conn = psycopg.connect(
        "postgresql://travelog:travelog@localhost:5432/travelog", autocommit=True
    )
    try:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = 'travelog_test'"
        ).fetchone()
        if not exists:
            conn.execute("CREATE DATABASE travelog_test")
    finally:
        conn.close()


_ensure_test_database()
command.upgrade(Config("alembic.ini"), "head")

from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services.s3_storage import get_s3_storage  # noqa: E402


@pytest.fixture(autouse=True)
def clean_tables():
    yield
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE diaries, photos, photo_groups, refresh_tokens, users "
                "RESTART IDENTITY CASCADE"
            )
        )


class FakeS3Storage:
    """실제 S3 대신 dict에 바이트를 보관하는 테스트 대역."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def presign_put(self, key: str, content_type: str) -> str:
        return f"https://fake-s3.local/{key}?method=put"

    def presign_get(self, key: str) -> str:
        return f"https://fake-s3.local/{key}?method=get"

    def get_object(self, key: str) -> bytes:
        if key not in self.objects:
            raise FileNotFoundError(key)
        return self.objects[key]


@pytest.fixture
def fake_s3():
    fake = FakeS3Storage()
    app.dependency_overrides[get_s3_storage] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_s3_storage, None)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
