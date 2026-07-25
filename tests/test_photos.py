from tests.photo_utils import BASE_LAT, BASE_LNG, auth_headers, make_jpeg, upload_photo

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
    assert body["group_id"] is None  # 그룹이 없으므로 미분류
    assert body["url"] is not None


def test_complete_without_gps_stores_null_coordinates(client, fake_s3):
    headers = auth_headers(client)

    res = upload_photo(client, headers, fake_s3, lat=None, lng=None)

    assert res.status_code == 200
    body = res.json()
    assert body["latitude"] is None
    assert body["longitude"] is None
    assert body["group_id"] is None


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
    assert body[0]["group_id"] is None


def test_unassigned_excludes_other_users(client, fake_s3):
    headers = auth_headers(client)
    upload_photo(client, headers, fake_s3)

    other_headers = auth_headers(client, email="other@example.com")
    res = client.get("/api/v1/photos/unassigned", headers=other_headers)

    assert res.status_code == 200
    assert res.json() == []
