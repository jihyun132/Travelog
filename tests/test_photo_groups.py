from tests.photo_utils import BASE_LAT, BASE_LNG, auth_headers, offset_lat, upload_photo


def create_group(client, headers, name="서울시청", lat=BASE_LAT, lng=BASE_LNG, radius=None):
    payload = {"name": name, "anchor_lat": lat, "anchor_lng": lng}
    if radius is not None:
        payload["radius_m"] = radius
    return client.post("/api/v1/photo-groups", headers=headers, json=payload)


# ── 그룹 생성/조회 ───────────────────────────────────────


def test_create_group(client, fake_s3):
    headers = auth_headers(client)

    res = create_group(client, headers)

    assert res.status_code == 201
    body = res.json()
    assert body["name"] == "서울시청"
    assert body["photo_count"] == 0
    assert body["thumbnail_url"] is None


def test_create_group_without_auth_returns_401(client):
    res = client.post(
        "/api/v1/photo-groups",
        json={"name": "서울시청", "anchor_lat": BASE_LAT, "anchor_lng": BASE_LNG},
    )

    assert res.status_code == 401


def test_get_other_users_group_returns_404(client, fake_s3):
    headers = auth_headers(client)
    group_id = create_group(client, headers).json()["id"]

    other_headers = auth_headers(client, email="other@example.com")
    res = client.get(f"/api/v1/photo-groups/{group_id}", headers=other_headers)

    assert res.status_code == 404


# ── 반경 기반 자동 배정 ──────────────────────────────────


def test_photo_within_radius_is_assigned(client, fake_s3):
    headers = auth_headers(client)
    group_id = create_group(client, headers).json()["id"]

    # 앵커에서 북쪽 20m — 기본 반경 30m 이내
    res = upload_photo(client, headers, fake_s3, lat=offset_lat(BASE_LAT, 20))

    assert res.json()["group_id"] == group_id


def test_photo_outside_radius_is_unassigned(client, fake_s3):
    headers = auth_headers(client)
    create_group(client, headers)

    res = upload_photo(client, headers, fake_s3, lat=offset_lat(BASE_LAT, 100))

    assert res.json()["group_id"] is None


def test_radius_boundary(client, fake_s3):
    headers = auth_headers(client)
    group_id = create_group(client, headers, radius=30).json()["id"]

    inside = upload_photo(client, headers, fake_s3, lat=offset_lat(BASE_LAT, 29))
    outside = upload_photo(
        client, headers, fake_s3, lat=offset_lat(BASE_LAT, 31), filename="out.jpg"
    )

    assert inside.json()["group_id"] == group_id
    assert outside.json()["group_id"] is None


def test_photo_in_two_radii_goes_to_closer_group(client, fake_s3):
    headers = auth_headers(client)
    create_group(client, headers, name="먼그룹", lat=offset_lat(BASE_LAT, 50), radius=100)
    near_id = create_group(client, headers, name="가까운그룹", lat=BASE_LAT, radius=100).json()[
        "id"
    ]

    # 가까운그룹 앵커에서 10m, 먼그룹 앵커에서 40m
    res = upload_photo(client, headers, fake_s3, lat=offset_lat(BASE_LAT, 10))

    assert res.json()["group_id"] == near_id


def test_photo_not_assigned_to_other_users_group(client, fake_s3):
    headers = auth_headers(client)
    create_group(client, headers)

    other_headers = auth_headers(client, email="other@example.com")
    res = upload_photo(client, other_headers, fake_s3)

    assert res.json()["group_id"] is None


# ── 그룹 생성/수정 시 재스캔 ─────────────────────────────


def test_create_group_absorbs_existing_unassigned_photos(client, fake_s3):
    headers = auth_headers(client)
    photo_id = upload_photo(client, headers, fake_s3).json()["id"]

    res = create_group(client, headers)

    assert res.json()["photo_count"] == 1
    detail = client.get(f"/api/v1/photo-groups/{res.json()['id']}", headers=headers).json()
    assert [p["id"] for p in detail["photos"]] == [photo_id]
    assert client.get("/api/v1/photos/unassigned", headers=headers).json() == []


def test_update_anchor_releases_and_absorbs(client, fake_s3):
    headers = auth_headers(client)
    group_id = create_group(client, headers).json()["id"]
    near = upload_photo(client, headers, fake_s3).json()  # 앵커 위치 → 편입
    far_lat = offset_lat(BASE_LAT, 500)
    far = upload_photo(client, headers, fake_s3, lat=far_lat, filename="far.jpg").json()
    assert near["group_id"] == group_id
    assert far["group_id"] is None

    # 앵커를 먼 사진 위치로 이동 → near는 방출, far는 편입
    res = client.patch(
        f"/api/v1/photo-groups/{group_id}", headers=headers, json={"anchor_lat": far_lat}
    )

    assert res.status_code == 200
    detail = client.get(f"/api/v1/photo-groups/{group_id}", headers=headers).json()
    assert [p["id"] for p in detail["photos"]] == [far["id"]]
    unassigned = client.get("/api/v1/photos/unassigned", headers=headers).json()
    assert [p["id"] for p in unassigned] == [near["id"]]


def test_delete_group_keeps_photos_as_unassigned(client, fake_s3):
    headers = auth_headers(client)
    group_id = create_group(client, headers).json()["id"]
    photo_id = upload_photo(client, headers, fake_s3).json()["id"]

    res = client.delete(f"/api/v1/photo-groups/{group_id}", headers=headers)

    assert res.status_code == 204
    unassigned = client.get("/api/v1/photos/unassigned", headers=headers).json()
    assert [p["id"] for p in unassigned] == [photo_id]


# ── 사진 순서 저장 ───────────────────────────────────────


def test_update_photo_order(client, fake_s3):
    headers = auth_headers(client)
    group_id = create_group(client, headers).json()["id"]
    first = upload_photo(client, headers, fake_s3, taken="2026:05:01 09:00:00").json()["id"]
    second = upload_photo(
        client, headers, fake_s3, taken="2026:05:01 10:00:00", filename="b.jpg"
    ).json()["id"]
    third = upload_photo(
        client, headers, fake_s3, taken="2026:05:01 11:00:00", filename="c.jpg"
    ).json()["id"]

    res = client.put(
        f"/api/v1/photo-groups/{group_id}/photos/order",
        headers=headers,
        json={"photo_ids": [third, first, second]},
    )

    assert res.status_code == 200
    assert [p["id"] for p in res.json()["photos"]] == [third, first, second]
    # 저장된 순서가 상세 조회에서도 유지된다
    detail = client.get(f"/api/v1/photo-groups/{group_id}", headers=headers).json()
    assert [p["id"] for p in detail["photos"]] == [third, first, second]


def test_photos_without_order_fall_back_to_taken_at(client, fake_s3):
    headers = auth_headers(client)
    group_id = create_group(client, headers).json()["id"]
    late = upload_photo(client, headers, fake_s3, taken="2026:05:02 10:00:00").json()["id"]
    early = upload_photo(
        client, headers, fake_s3, taken="2026:05:01 10:00:00", filename="b.jpg"
    ).json()["id"]

    detail = client.get(f"/api/v1/photo-groups/{group_id}", headers=headers).json()

    assert [p["id"] for p in detail["photos"]] == [early, late]


def test_update_order_with_mismatched_ids_returns_422(client, fake_s3):
    headers = auth_headers(client)
    group_id = create_group(client, headers).json()["id"]
    photo_id = upload_photo(client, headers, fake_s3).json()["id"]

    missing = client.put(
        f"/api/v1/photo-groups/{group_id}/photos/order",
        headers=headers,
        json={"photo_ids": [photo_id, 99999]},
    )
    duplicated = client.put(
        f"/api/v1/photo-groups/{group_id}/photos/order",
        headers=headers,
        json={"photo_ids": [photo_id, photo_id]},
    )

    assert missing.status_code == 422
    assert duplicated.status_code == 422


def test_update_order_on_other_users_group_returns_404(client, fake_s3):
    headers = auth_headers(client)
    group_id = create_group(client, headers).json()["id"]

    other_headers = auth_headers(client, email="other@example.com")
    res = client.put(
        f"/api/v1/photo-groups/{group_id}/photos/order",
        headers=other_headers,
        json={"photo_ids": [1]},
    )

    assert res.status_code == 404
