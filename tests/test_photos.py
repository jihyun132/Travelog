from tests.photo_utils import (
    BASE_LAT,
    BASE_LNG,
    auth_headers,
    create_place,
    create_trip,
    make_jpeg,
    offset_lat,
    upload_photo,
)

# ── presign ──────────────────────────────────────────────


def test_presign_returns_upload_url(client, fake_s3):
    headers = auth_headers(client)

    res = client.post(
        "/api/v1/photos/presign",
        headers=headers,
        json={"filename": "trip.jpg", "content_type": "image/jpeg"},
    )

    assert res.status_code == 201
    body = res.json()
    assert body["photo_id"] > 0
    assert body["s3_key"].startswith("users/")
    assert body["upload_url"].startswith("https://")


def test_presign_rejects_non_image_content_type(client, fake_s3):
    headers = auth_headers(client)

    res = client.post(
        "/api/v1/photos/presign",
        headers=headers,
        json={"filename": "note.txt", "content_type": "text/plain"},
    )

    assert res.status_code == 422


def test_presign_without_auth_returns_401(client, fake_s3):
    res = client.post(
        "/api/v1/photos/presign",
        json={"filename": "trip.jpg", "content_type": "image/jpeg"},
    )

    assert res.status_code == 401


# ── complete (EXIF 추출) ─────────────────────────────────


def test_complete_extracts_gps_and_taken_at(client, fake_s3):
    headers = auth_headers(client)

    res = upload_photo(client, headers, fake_s3)

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "COMPLETED"
    assert abs(body["latitude"] - BASE_LAT) < 1e-5
    assert abs(body["longitude"] - BASE_LNG) < 1e-5
    assert body["taken_at"] == "2026-05-01T10:30:00"
    assert body["place_id"] is None  # 방문지가 없으므로 미분류
    assert body["url"] is not None


def test_complete_without_gps_stores_null_coordinates(client, fake_s3):
    headers = auth_headers(client)

    res = upload_photo(client, headers, fake_s3, lat=None, lng=None)

    assert res.status_code == 200
    body = res.json()
    assert body["latitude"] is None
    assert body["longitude"] is None
    assert body["place_id"] is None


def test_complete_non_image_returns_400(client, fake_s3):
    headers = auth_headers(client)

    res = upload_photo(client, headers, fake_s3, data=b"not an image")

    assert res.status_code == 400
    assert res.json()["code"] == "INVALID_PHOTO"


def test_complete_before_s3_upload_returns_400(client, fake_s3):
    headers = auth_headers(client)
    presign = client.post(
        "/api/v1/photos/presign",
        headers=headers,
        json={"filename": "trip.jpg", "content_type": "image/jpeg"},
    )

    res = client.post(f"/api/v1/photos/{presign.json()['photo_id']}/complete", headers=headers)

    assert res.status_code == 400
    assert res.json()["code"] == "INVALID_PHOTO"


def test_complete_other_users_photo_returns_404(client, fake_s3):
    headers = auth_headers(client)
    presign = client.post(
        "/api/v1/photos/presign",
        headers=headers,
        json={"filename": "trip.jpg", "content_type": "image/jpeg"},
    )
    fake_s3.objects[presign.json()["s3_key"]] = make_jpeg()

    other_headers = auth_headers(client, email="other@example.com")
    res = client.post(
        f"/api/v1/photos/{presign.json()['photo_id']}/complete", headers=other_headers
    )

    assert res.status_code == 404


# ── 미분류 목록 ──────────────────────────────────────────


def test_unassigned_lists_only_completed_ungrouped_photos(client, fake_s3):
    headers = auth_headers(client)
    upload_photo(client, headers, fake_s3)
    # PENDING 상태(complete 전) 사진은 목록에 나오지 않아야 한다
    client.post(
        "/api/v1/photos/presign",
        headers=headers,
        json={"filename": "pending.jpg", "content_type": "image/jpeg"},
    )

    res = client.get("/api/v1/photos/unassigned", headers=headers)

    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["place_id"] is None


def test_unassigned_excludes_other_users(client, fake_s3):
    headers = auth_headers(client)
    upload_photo(client, headers, fake_s3)

    other_headers = auth_headers(client, email="other@example.com")
    res = client.get("/api/v1/photos/unassigned", headers=other_headers)

    assert res.status_code == 200
    assert res.json() == []


# ── 명시 배정 (업로드 플로우) ────────────────────────────


def test_complete_with_place_id_assigns_explicitly(client, fake_s3):
    headers = auth_headers(client)
    place_id = create_place(client, headers).json()["id"]

    # 반경 밖(500m)이어도 명시 배정이면 그 방문지로 들어간다
    res = upload_photo(client, headers, fake_s3, lat=offset_lat(BASE_LAT, 500), place_id=place_id)

    assert res.status_code == 200
    assert res.json()["place_id"] == place_id


def test_complete_with_place_id_wins_over_radius_match(client, fake_s3):
    """재방문 지역에서 과거 여행의 방문지로 흡수되지 않아야 한다."""
    headers = auth_headers(client)
    old_place = create_place(client, headers, name="작년에 온 곳").json()["id"]
    new_trip = create_trip(client, headers, title="이번 여행")
    new_place = create_place(client, headers, new_trip, name="이번에 온 곳").json()["id"]

    res = upload_photo(client, headers, fake_s3, place_id=new_place)

    assert res.json()["place_id"] == new_place
    assert res.json()["place_id"] != old_place


def test_complete_with_other_users_place_returns_404(client, fake_s3):
    headers = auth_headers(client)
    place_id = create_place(client, headers).json()["id"]

    other_headers = auth_headers(client, email="other@example.com")
    res = upload_photo(client, other_headers, fake_s3, place_id=place_id)

    assert res.status_code == 404


def test_complete_without_gps_still_assigns_when_place_id_given(client, fake_s3):
    """EXIF GPS가 없어도 클라이언트가 방문지를 지정하면 배정된다 (SRS 5.1)."""
    headers = auth_headers(client)
    place_id = create_place(client, headers).json()["id"]

    res = upload_photo(client, headers, fake_s3, lat=None, lng=None, place_id=place_id)

    assert res.status_code == 200
    body = res.json()
    assert body["place_id"] == place_id
    assert body["latitude"] is None
