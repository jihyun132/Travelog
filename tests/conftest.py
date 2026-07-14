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


@pytest.fixture(autouse=True)
def clean_tables():
    yield
    with engine.begin() as conn:
        conn.execute(
            text("TRUNCATE TABLE photo_locations, refresh_tokens, users RESTART IDENTITY CASCADE")
        )


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
