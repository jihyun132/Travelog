from tests.photo_utils import BASE_LAT, auth_headers, create_place, create_trip, upload_photo

# ── 여행 CRUD ────────────────────────────────────────────


def test_create_trip(client, fake_s3):
    headers = auth_headers(client)

    res = client.post(
        "/api/v1/trips",
        headers=headers,
        json={
            "title": "오사카 여행",
            "start_date": "2026-05-01",
            "end_date": "2026-05-04",
            "hashtags": ["일본", "벚꽃"],
        },
    )

    assert res.status_code == 201
    body = res.json()
    assert body["title"] == "오사카 여행"
    assert body["hashtags"] == ["일본", "벚꽃"]
    assert body["is_public"] is False
    assert body["place_count"] == 0


def test_create_trip_without_dates(client, fake_s3):
    """기간은 사진 업로드 전에는 알 수 없으므로 비워둘 수 있다."""
    headers = auth_headers(client)

    res = client.post("/api/v1/trips", headers=headers, json={"title": "무계획 여행"})

    assert res.status_code == 201
    assert res.json()["start_date"] is None
    assert res.json()["end_date"] is None


def test_create_trip_with_end_before_start_returns_422(client, fake_s3):
    headers = auth_headers(client)

    res = client.post(
        "/api/v1/trips",
        headers=headers,
        json={"title": "거꾸로 여행", "start_date": "2026-05-04", "end_date": "2026-05-01"},
    )

    assert res.status_code == 422


def test_create_trip_without_auth_returns_401(client):
    res = client.post("/api/v1/trips", json={"title": "오사카 여행"})

    assert res.status_code == 401


def test_list_trips_returns_only_own(client, fake_s3):
    headers = auth_headers(client)
    create_trip(client, headers, title="내 여행")

    other_headers = auth_headers(client, email="other@example.com")
    res = client.get("/api/v1/trips", headers=other_headers)

    assert res.status_code == 200
    assert res.json() == []


def test_get_trip_includes_place_count_and_thumbnail(client, fake_s3):
    headers = auth_headers(client)
    trip_id = create_trip(client, headers)
    create_place(client, headers, trip_id)
    upload_photo(client, headers, fake_s3)

    res = client.get(f"/api/v1/trips/{trip_id}", headers=headers)

    assert res.status_code == 200
    body = res.json()
    assert body["place_count"] == 1
    assert body["thumbnail_url"] is not None


def test_get_other_users_trip_returns_404(client, fake_s3):
    headers = auth_headers(client)
    trip_id = create_trip(client, headers)

    other_headers = auth_headers(client, email="other@example.com")
    res = client.get(f"/api/v1/trips/{trip_id}", headers=other_headers)

    assert res.status_code == 404


def test_update_trip(client, fake_s3):
    headers = auth_headers(client)
    trip_id = create_trip(client, headers)

    res = client.patch(
        f"/api/v1/trips/{trip_id}",
        headers=headers,
        json={"title": "수정된 제목", "is_public": True},
    )

    assert res.status_code == 200
    assert res.json()["title"] == "수정된 제목"
    assert res.json()["is_public"] is True


def test_update_trip_with_invalid_period_returns_422(client, fake_s3):
    """부분 수정이라 기존 값과 병합한 뒤의 기간을 검증한다."""
    headers = auth_headers(client)
    trip_id = create_trip(client, headers, start_date="2026-05-01", end_date="2026-05-04")

    res = client.patch(f"/api/v1/trips/{trip_id}", headers=headers, json={"end_date": "2026-04-01"})

    assert res.status_code == 422


def test_delete_trip_removes_places_and_keeps_photos(client, fake_s3):
    headers = auth_headers(client)
    trip_id = create_trip(client, headers)
    place_id = create_place(client, headers, trip_id).json()["id"]
    photo_id = upload_photo(client, headers, fake_s3).json()["id"]

    res = client.delete(f"/api/v1/trips/{trip_id}", headers=headers)

    assert res.status_code == 204
    assert client.get(f"/api/v1/places/{place_id}", headers=headers).status_code == 404
    unassigned = client.get("/api/v1/photos/unassigned", headers=headers).json()
    assert [p["id"] for p in unassigned] == [photo_id]


def test_delete_other_users_trip_returns_404(client, fake_s3):
    headers = auth_headers(client)
    trip_id = create_trip(client, headers)

    other_headers = auth_headers(client, email="other@example.com")
    res = client.delete(f"/api/v1/trips/{trip_id}", headers=other_headers)

    assert res.status_code == 404


# ── 지구본 조회 (SRS 1.1~1.2) ────────────────────────────


def test_globe_returns_trips_with_places_in_visit_order(client, fake_s3):
    headers = auth_headers(client)
    trip_id = create_trip(client, headers, title="오사카 여행")
    first = create_place(client, headers, trip_id, name="오사카성", lat=BASE_LAT).json()["id"]
    second = create_place(client, headers, trip_id, name="도톤보리", lat=BASE_LAT + 0.1).json()[
        "id"
    ]

    res = client.get("/api/v1/globe", headers=headers)

    assert res.status_code == 200
    trips = res.json()["trips"]
    assert len(trips) == 1
    assert trips[0]["title"] == "오사카 여행"
    assert [p["id"] for p in trips[0]["places"]] == [first, second]
    assert [p["visit_order"] for p in trips[0]["places"]] == [1, 2]
    assert [p["name"] for p in trips[0]["places"]] == ["오사카성", "도톤보리"]


def test_globe_reflects_visited_state(client, fake_s3):
    headers = auth_headers(client)
    trip_id = create_trip(client, headers)
    visited = create_place(client, headers, trip_id, name="다녀온곳", lat=BASE_LAT).json()["id"]
    create_place(client, headers, trip_id, name="예정지", lat=BASE_LAT + 0.1)
    client.patch(f"/api/v1/places/{visited}/visit", headers=headers, json={"is_visited": True})

    places = client.get("/api/v1/globe", headers=headers).json()["trips"][0]["places"]

    assert [p["is_visited"] for p in places] == [True, False]


def test_globe_includes_trip_without_places(client, fake_s3):
    headers = auth_headers(client)
    create_trip(client, headers)

    trips = client.get("/api/v1/globe", headers=headers).json()["trips"]

    assert len(trips) == 1
    assert trips[0]["places"] == []


def test_globe_excludes_other_users_trips(client, fake_s3):
    headers = auth_headers(client)
    trip_id = create_trip(client, headers)
    create_place(client, headers, trip_id)

    other_headers = auth_headers(client, email="other@example.com")
    res = client.get("/api/v1/globe", headers=other_headers)

    assert res.status_code == 200
    assert res.json()["trips"] == []


def test_globe_without_auth_returns_401(client):
    res = client.get("/api/v1/globe")

    assert res.status_code == 401


# ── 통합 상세 (GET /trips/{id}/detail) ───────────────────


def test_trip_detail_returns_places_photos_and_diaries(client, fake_s3):
    """화면 하나가 필요한 데이터를 한 번의 호출로 받는다."""
    headers = auth_headers(client)
    trip_id = create_trip(client, headers)
    place_id = create_place(client, headers, trip_id).json()["id"]
    upload_photo(client, headers, fake_s3, place_id=place_id)
    client.put(
        f"/api/v1/places/{place_id}/diary",
        headers=headers,
        json={"content": "좋았다", "weather": "SUNNY"},
    )

    res = client.get(f"/api/v1/trips/{trip_id}/detail", headers=headers)

    assert res.status_code == 200
    body = res.json()
    assert body["place_count"] == 1
    assert body["photo_count"] == 1
    assert body["last_taken_at"] == "2026-05-01T10:30:00"
    assert len(body["places"]) == 1
    assert body["places"][0]["id"] == place_id
    assert len(body["places"][0]["photos"]) == 1
    assert body["places"][0]["photos"][0]["url"] is not None
    assert body["places"][0]["first_taken_at"] == "2026-05-01T10:30:00"
    assert len(body["diaries"]) == 1
    assert body["diaries"][0]["place_id"] == place_id
    assert body["diaries"][0]["content"] == "좋았다"


def test_trip_detail_empty_trip(client, fake_s3):
    headers = auth_headers(client)
    trip_id = create_trip(client, headers)

    body = client.get(f"/api/v1/trips/{trip_id}/detail", headers=headers).json()

    assert body["places"] == []
    assert body["diaries"] == []
    assert body["photo_count"] == 0
    assert body["last_taken_at"] is None


def test_trip_detail_of_other_user_returns_404(client, fake_s3):
    headers = auth_headers(client)
    trip_id = create_trip(client, headers)

    other_headers = auth_headers(client, email="other@example.com")
    res = client.get(f"/api/v1/trips/{trip_id}/detail", headers=other_headers)

    assert res.status_code == 404


def test_trip_detail_without_auth_returns_401(client, fake_s3):
    res = client.get("/api/v1/trips/1/detail")

    assert res.status_code == 401


# ── country / cover_photo_id / manual_status ─────────────


def test_create_trip_stores_country(client, fake_s3):
    headers = auth_headers(client)

    res = client.post(
        "/api/v1/trips", headers=headers, json={"title": "오사카 여행", "country": "Japan"}
    )

    assert res.status_code == 201
    assert res.json()["country"] == "Japan"


def test_update_manual_status_and_reset_to_auto(client, fake_s3):
    headers = auth_headers(client)
    trip_id = create_trip(client, headers)

    manual = client.patch(
        f"/api/v1/trips/{trip_id}", headers=headers, json={"manual_status": "ON_TRIP"}
    )
    assert manual.json()["manual_status"] == "ON_TRIP"

    # null을 명시하면 수동 지정을 해제하고 자동 판정으로 되돌린다
    auto = client.patch(f"/api/v1/trips/{trip_id}", headers=headers, json={"manual_status": None})
    assert auto.json()["manual_status"] is None


def test_invalid_manual_status_returns_422(client, fake_s3):
    headers = auth_headers(client)
    trip_id = create_trip(client, headers)

    res = client.patch(
        f"/api/v1/trips/{trip_id}", headers=headers, json={"manual_status": "RESTING"}
    )

    assert res.status_code == 422


def test_cover_photo_overrides_thumbnail(client, fake_s3):
    headers = auth_headers(client)
    trip_id = create_trip(client, headers)
    place_id = create_place(client, headers, trip_id).json()["id"]
    upload_photo(client, headers, fake_s3, place_id=place_id, filename="first.jpg")
    second = upload_photo(client, headers, fake_s3, place_id=place_id, filename="second.jpg").json()

    res = client.patch(
        f"/api/v1/trips/{trip_id}", headers=headers, json={"cover_photo_id": second["id"]}
    )

    assert res.status_code == 200
    body = res.json()
    assert body["cover_photo_id"] == second["id"]
    assert "second.jpg" not in body["thumbnail_url"]  # s3_key는 uuid 기반
    assert body["thumbnail_url"] is not None


def test_cover_photo_from_other_trip_returns_422(client, fake_s3):
    headers = auth_headers(client)
    other_trip = create_trip(client, headers, title="다른 여행")
    other_place = create_place(client, headers, other_trip).json()["id"]
    foreign_photo = upload_photo(client, headers, fake_s3, place_id=other_place).json()

    trip_id = create_trip(client, headers)
    res = client.patch(
        f"/api/v1/trips/{trip_id}", headers=headers, json={"cover_photo_id": foreign_photo["id"]}
    )

    assert res.status_code == 422
