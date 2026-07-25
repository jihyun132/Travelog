from sqlalchemy import text

from app.db.session import engine
from tests.photo_utils import BASE_LAT, BASE_LNG, auth_headers


def create_group(client, headers, name="서울시청"):
    res = client.post(
        "/api/v1/photo-groups",
        headers=headers,
        json={"name": name, "anchor_lat": BASE_LAT, "anchor_lng": BASE_LNG},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def put_diary(client, headers, group_id, content="시청 앞 광장 산책", weather="SUNNY"):
    payload = {"content": content}
    if weather is not None:
        payload["weather"] = weather
    return client.put(f"/api/v1/photo-groups/{group_id}/diary", headers=headers, json=payload)


# ── 작성/조회 ────────────────────────────────────────────


def test_write_and_get_diary(client, fake_s3):
    headers = auth_headers(client)
    group_id = create_group(client, headers)

    res = put_diary(client, headers, group_id)

    assert res.status_code == 200
    body = res.json()
    assert body["group_id"] == group_id
    assert body["content"] == "시청 앞 광장 산책"
    assert body["weather"] == "SUNNY"

    fetched = client.get(f"/api/v1/photo-groups/{group_id}/diary", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]


def test_write_diary_without_weather(client, fake_s3):
    headers = auth_headers(client)
    group_id = create_group(client, headers)

    res = put_diary(client, headers, group_id, weather=None)

    assert res.status_code == 200
    assert res.json()["weather"] is None


def test_rewrite_overwrites_existing_diary(client, fake_s3):
    headers = auth_headers(client)
    group_id = create_group(client, headers)
    first = put_diary(client, headers, group_id).json()

    res = put_diary(client, headers, group_id, content="수정된 일기", weather="RAINY")

    assert res.status_code == 200
    body = res.json()
    assert body["id"] == first["id"]  # 새로 만들지 않고 덮어쓴다
    assert body["content"] == "수정된 일기"
    assert body["weather"] == "RAINY"


def test_get_diary_before_write_returns_404(client, fake_s3):
    headers = auth_headers(client)
    group_id = create_group(client, headers)

    res = client.get(f"/api/v1/photo-groups/{group_id}/diary", headers=headers)

    assert res.status_code == 404


def test_write_diary_without_auth_returns_401(client):
    res = client.put("/api/v1/photo-groups/1/diary", json={"content": "산책", "weather": "SUNNY"})

    assert res.status_code == 401


def test_write_diary_on_other_users_group_returns_404(client, fake_s3):
    headers = auth_headers(client)
    group_id = create_group(client, headers)

    other_headers = auth_headers(client, email="other@example.com")
    res = put_diary(client, other_headers, group_id)

    assert res.status_code == 404


def test_invalid_weather_returns_422(client, fake_s3):
    headers = auth_headers(client)
    group_id = create_group(client, headers)

    res = put_diary(client, headers, group_id, weather="WINDY")

    assert res.status_code == 422


# ── 삭제 ─────────────────────────────────────────────────


def test_delete_diary(client, fake_s3):
    headers = auth_headers(client)
    group_id = create_group(client, headers)
    put_diary(client, headers, group_id)

    res = client.delete(f"/api/v1/photo-groups/{group_id}/diary", headers=headers)

    assert res.status_code == 204
    assert client.get(f"/api/v1/photo-groups/{group_id}/diary", headers=headers).status_code == 404


def test_delete_diary_before_write_returns_404(client, fake_s3):
    headers = auth_headers(client)
    group_id = create_group(client, headers)

    res = client.delete(f"/api/v1/photo-groups/{group_id}/diary", headers=headers)

    assert res.status_code == 404


def test_delete_group_hard_deletes_diary(client, fake_s3):
    headers = auth_headers(client)
    group_id = create_group(client, headers)
    put_diary(client, headers, group_id)

    res = client.delete(f"/api/v1/photo-groups/{group_id}", headers=headers)

    assert res.status_code == 204
    # 그룹이 사라지면 API로는 확인할 수 없으므로 DB에서 직접 하드 삭제를 검증한다
    with engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM diaries")).scalar()
    assert count == 0
