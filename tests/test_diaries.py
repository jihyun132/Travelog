from sqlalchemy import text

from app.db.session import engine
from tests.photo_utils import auth_headers, create_place


def put_diary(client, headers, place_id, content="시청 앞 광장 산책", weather="SUNNY"):
    payload = {"content": content}
    if weather is not None:
        payload["weather"] = weather
    return client.put(f"/api/v1/places/{place_id}/diary", headers=headers, json=payload)


# ── 작성/조회 ────────────────────────────────────────────


def test_write_and_get_diary(client, fake_s3):
    headers = auth_headers(client)
    place_id = create_place(client, headers).json()["id"]

    res = put_diary(client, headers, place_id)

    assert res.status_code == 200
    body = res.json()
    assert body["place_id"] == place_id
    assert body["content"] == "시청 앞 광장 산책"
    assert body["weather"] == "SUNNY"

    fetched = client.get(f"/api/v1/places/{place_id}/diary", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]


def test_write_diary_without_weather(client, fake_s3):
    headers = auth_headers(client)
    place_id = create_place(client, headers).json()["id"]

    res = put_diary(client, headers, place_id, weather=None)

    assert res.status_code == 200
    assert res.json()["weather"] is None


def test_rewrite_overwrites_existing_diary(client, fake_s3):
    headers = auth_headers(client)
    place_id = create_place(client, headers).json()["id"]
    first = put_diary(client, headers, place_id).json()

    res = put_diary(client, headers, place_id, content="수정된 일기", weather="RAINY")

    assert res.status_code == 200
    body = res.json()
    assert body["id"] == first["id"]  # 새로 만들지 않고 덮어쓴다
    assert body["content"] == "수정된 일기"
    assert body["weather"] == "RAINY"


def test_get_diary_before_write_returns_404(client, fake_s3):
    headers = auth_headers(client)
    place_id = create_place(client, headers).json()["id"]

    res = client.get(f"/api/v1/places/{place_id}/diary", headers=headers)

    assert res.status_code == 404


def test_write_diary_without_auth_returns_401(client):
    res = client.put("/api/v1/places/1/diary", json={"content": "산책", "weather": "SUNNY"})

    assert res.status_code == 401


def test_write_diary_on_other_users_place_returns_404(client, fake_s3):
    headers = auth_headers(client)
    place_id = create_place(client, headers).json()["id"]

    other_headers = auth_headers(client, email="other@example.com")
    res = put_diary(client, other_headers, place_id)

    assert res.status_code == 404


def test_invalid_weather_returns_422(client, fake_s3):
    headers = auth_headers(client)
    place_id = create_place(client, headers).json()["id"]

    res = put_diary(client, headers, place_id, weather="WINDY")

    assert res.status_code == 422


# ── 삭제 ─────────────────────────────────────────────────


def test_delete_diary(client, fake_s3):
    headers = auth_headers(client)
    place_id = create_place(client, headers).json()["id"]
    put_diary(client, headers, place_id)

    res = client.delete(f"/api/v1/places/{place_id}/diary", headers=headers)

    assert res.status_code == 204
    assert client.get(f"/api/v1/places/{place_id}/diary", headers=headers).status_code == 404


def test_delete_diary_before_write_returns_404(client, fake_s3):
    headers = auth_headers(client)
    place_id = create_place(client, headers).json()["id"]

    res = client.delete(f"/api/v1/places/{place_id}/diary", headers=headers)

    assert res.status_code == 404


def test_delete_place_hard_deletes_diary(client, fake_s3):
    headers = auth_headers(client)
    place_id = create_place(client, headers).json()["id"]
    put_diary(client, headers, place_id)

    res = client.delete(f"/api/v1/places/{place_id}", headers=headers)

    assert res.status_code == 204
    # 방문지가 사라지면 API로는 확인할 수 없으므로 DB에서 직접 하드 삭제를 검증한다
    with engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM diaries")).scalar()
    assert count == 0


def test_delete_trip_hard_deletes_diary(client, fake_s3):
    """여행 삭제 시 방문지가 CASCADE로 지워지며 일기도 함께 사라진다."""
    headers = auth_headers(client)
    place = create_place(client, headers).json()
    put_diary(client, headers, place["id"])

    res = client.delete(f"/api/v1/trips/{place['trip_id']}", headers=headers)

    assert res.status_code == 204
    with engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM diaries")).scalar()
    assert count == 0


def test_weather_only_diary_is_allowed(client, fake_s3):
    """본문 없이 날씨만 기록하는 저장을 허용한다 (프론트 일기 화면이 이를 허용)."""
    headers = auth_headers(client)
    place_id = create_place(client, headers).json()["id"]

    res = put_diary(client, headers, place_id, content="", weather="SNOWY")

    assert res.status_code == 200
    body = res.json()
    assert body["content"] == ""
    assert body["weather"] == "SNOWY"
