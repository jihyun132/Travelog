"""공개 여행 탐색 (SRS 1.4, P2) — 검색 / 상세 / 내 여행으로 가져오기."""

from tests.photo_utils import BASE_LAT, auth_headers, create_place, create_trip, upload_photo


def make_public_trip(
    client, headers, *, title="오사카 여행", country="Japan", places=("도톤보리",)
):
    """공개 여행 1건을 만들고 id를 반환한다."""
    trip_id = create_trip(client, headers, title=title, country=country, hashtags=["먹방"])
    for index, name in enumerate(places):
        create_place(client, headers, trip_id, name=name, lat=BASE_LAT + index * 0.01)
    client.patch(f"/api/v1/trips/{trip_id}", headers=headers, json={"is_public": True})
    return trip_id


# ── 검색 ─────────────────────────────────────────────────


def test_search_finds_public_trip_by_title(client, fake_s3):
    headers = auth_headers(client)
    trip_id = make_public_trip(client, headers)

    res = client.get("/api/v1/explore/trips", params={"q": "오사카"})

    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["id"] == trip_id
    assert body[0]["owner_name"] == "여행자"
    assert body[0]["place_count"] == 1


def test_search_matches_country_hashtag_and_place_name(client, fake_s3):
    headers = auth_headers(client)
    make_public_trip(client, headers)

    assert len(client.get("/api/v1/explore/trips", params={"q": "japan"}).json()) == 1
    assert len(client.get("/api/v1/explore/trips", params={"q": "먹방"}).json()) == 1
    assert len(client.get("/api/v1/explore/trips", params={"q": "도톤보리"}).json()) == 1


def test_search_excludes_private_trips(client, fake_s3):
    headers = auth_headers(client)
    create_trip(client, headers, title="비공개 오사카 여행")

    res = client.get("/api/v1/explore/trips", params={"q": "오사카"})

    assert res.json() == []


def test_search_with_empty_keyword_returns_empty(client, fake_s3):
    headers = auth_headers(client)
    make_public_trip(client, headers)

    assert client.get("/api/v1/explore/trips", params={"q": "   "}).json() == []


def test_search_allows_guest(client, fake_s3):
    """게스트도 공개 조회는 가능하다 (SRS 0.3.2)."""
    headers = auth_headers(client)
    make_public_trip(client, headers)

    res = client.get("/api/v1/explore/trips", params={"q": "오사카"})

    assert res.status_code == 200
    assert len(res.json()) == 1


# ── 상세 ─────────────────────────────────────────────────


def test_public_trip_detail_returns_route(client, fake_s3):
    headers = auth_headers(client)
    trip_id = make_public_trip(client, headers, places=("도톤보리", "오사카성", "쿠로몬"))

    res = client.get(f"/api/v1/explore/trips/{trip_id}")

    assert res.status_code == 200
    body = res.json()
    assert [p["name"] for p in body["places"]] == ["도톤보리", "오사카성", "쿠로몬"]
    assert [p["visit_order"] for p in body["places"]] == [1, 2, 3]


def test_private_trip_detail_returns_404(client, fake_s3):
    headers = auth_headers(client)
    trip_id = create_trip(client, headers)

    res = client.get(f"/api/v1/explore/trips/{trip_id}")

    assert res.status_code == 404


# ── 가져오기 (딥카피) ────────────────────────────────────


def test_import_copies_trip_and_places(client, fake_s3):
    owner = auth_headers(client)
    trip_id = make_public_trip(client, owner, places=("도톤보리", "오사카성"))

    importer = auth_headers(client, email="other@example.com")
    res = client.post(f"/api/v1/explore/trips/{trip_id}/import", headers=importer)

    assert res.status_code == 201
    body = res.json()
    assert body["id"] != trip_id
    assert body["title"] == "오사카 여행"
    assert body["country"] == "Japan"
    assert body["place_count"] == 2
    # 가져온 여행은 내가 공개하기 전까지 비공개다
    assert body["is_public"] is False

    places = client.get(f"/api/v1/trips/{body['id']}/places", headers=importer).json()
    assert [p["name"] for p in places] == ["도톤보리", "오사카성"]
    # 아직 가보지 않은 계획이므로 미방문으로 초기화된다 (SRS 1.4.3)
    assert all(p["is_visited"] is False for p in places)


def test_import_does_not_copy_photos_or_diaries(client, fake_s3):
    owner = auth_headers(client)
    trip_id = make_public_trip(client, owner)
    place_id = client.get(f"/api/v1/trips/{trip_id}/places", headers=owner).json()[0]["id"]
    upload_photo(client, owner, fake_s3, place_id=place_id)
    client.put(
        f"/api/v1/places/{place_id}/diary",
        headers=owner,
        json={"content": "원본 일기", "weather": "SUNNY"},
    )

    importer = auth_headers(client, email="other@example.com")
    copied_id = client.post(f"/api/v1/explore/trips/{trip_id}/import", headers=importer).json()[
        "id"
    ]

    detail = client.get(f"/api/v1/trips/{copied_id}/detail", headers=importer).json()
    assert detail["photo_count"] == 0
    assert detail["diaries"] == []
    assert detail["places"][0]["photos"] == []


def test_import_marks_source_visited_state_as_unvisited(client, fake_s3):
    owner = auth_headers(client)
    trip_id = make_public_trip(client, owner)
    place_id = client.get(f"/api/v1/trips/{trip_id}/places", headers=owner).json()[0]["id"]
    client.patch(f"/api/v1/places/{place_id}/visit", headers=owner, json={"is_visited": True})

    importer = auth_headers(client, email="other@example.com")
    copied_id = client.post(f"/api/v1/explore/trips/{trip_id}/import", headers=importer).json()[
        "id"
    ]

    places = client.get(f"/api/v1/trips/{copied_id}/places", headers=importer).json()
    assert places[0]["is_visited"] is False


def test_import_without_auth_returns_401(client, fake_s3):
    owner = auth_headers(client)
    trip_id = make_public_trip(client, owner)

    res = client.post(f"/api/v1/explore/trips/{trip_id}/import")

    assert res.status_code == 401


def test_import_private_trip_returns_404(client, fake_s3):
    owner = auth_headers(client)
    trip_id = create_trip(client, owner)

    importer = auth_headers(client, email="other@example.com")
    res = client.post(f"/api/v1/explore/trips/{trip_id}/import", headers=importer)

    assert res.status_code == 404
