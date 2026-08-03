"""핵심 플로우 통합 테스트: 가입 → 로그인 → 여행 → 사진 업로드 → 일기 저장.

프론트(uploadService.saveDraft / PlaceDetailPage)가 실제로 보내는 호출 순서를
그대로 재현해, 화면이 의존하는 계약이 서버에서 실제로 성립하는지 확인한다.
"""

from tests.photo_utils import BASE_LAT, BASE_LNG, make_jpeg, offset_lat
from tests.test_auth import login, signup

# 같은 방문지로 묶이는 거리(기본 반경 300m 이내)
NEARBY_OFFSET_M = 50
# 다른 방문지로 갈라지는 거리
FAR_OFFSET_M = 2000


def _presign_put_complete(client, headers, fake_s3, *, lat, lng, taken, place_id, filename):
    """프론트 apis/photos.uploadPhoto와 같은 3단계: presign → S3 PUT → 완료 통보."""
    presign = client.post(
        "/api/v1/photos/presign",
        headers=headers,
        json={"filename": filename, "content_type": "image/jpeg"},
    )
    assert presign.status_code == 201, presign.text
    body = presign.json()

    # 브라우저가 presigned URL로 S3에 직접 올리는 단계 (테스트에서는 fake S3에 바로 적재)
    fake_s3.objects[body["s3_key"]] = make_jpeg(lat, lng, taken)

    complete = client.post(
        f"/api/v1/photos/{body['photo_id']}/complete",
        headers=headers,
        json={"place_id": place_id},
    )
    assert complete.status_code == 200, complete.text
    return complete.json()


def test_signup_to_diary_full_flow(client, fake_s3):
    # 1) 가입 → 로그인
    assert signup(client).status_code == 201
    tokens = login(client).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    # 2) 여행 생성 (프론트가 EXIF에서 뽑은 기간 + 역지오코딩한 국가를 함께 보낸다)
    trip = client.post(
        "/api/v1/trips",
        headers=headers,
        json={
            "title": "서울 여행",
            "start_date": "2026-05-01",
            "end_date": "2026-05-02",
            "country": "South Korea",
        },
    )
    assert trip.status_code == 201, trip.text
    trip_id = trip.json()["id"]

    # 3) 클러스터마다 방문지 생성 → 그 방문지로 사진 명시 배정
    first_place = client.post(
        f"/api/v1/trips/{trip_id}/places",
        headers=headers,
        json={"name": "서울시청", "anchor_lat": BASE_LAT, "anchor_lng": BASE_LNG, "radius_m": 300},
    )
    assert first_place.status_code == 201, first_place.text
    first_place_id = first_place.json()["id"]

    second_place = client.post(
        f"/api/v1/trips/{trip_id}/places",
        headers=headers,
        json={
            "name": "남산",
            "anchor_lat": offset_lat(BASE_LAT, FAR_OFFSET_M),
            "anchor_lng": BASE_LNG,
            "radius_m": 300,
        },
    )
    second_place_id = second_place.json()["id"]

    photo1 = _presign_put_complete(
        client,
        headers,
        fake_s3,
        lat=BASE_LAT,
        lng=BASE_LNG,
        taken="2026:05:01 10:30:00",
        place_id=first_place_id,
        filename="a.jpg",
    )
    _presign_put_complete(
        client,
        headers,
        fake_s3,
        lat=offset_lat(BASE_LAT, NEARBY_OFFSET_M),
        lng=BASE_LNG,
        taken="2026:05:01 11:00:00",
        place_id=first_place_id,
        filename="b.jpg",
    )
    _presign_put_complete(
        client,
        headers,
        fake_s3,
        lat=offset_lat(BASE_LAT, FAR_OFFSET_M),
        lng=BASE_LNG,
        taken="2026:05:02 09:00:00",
        place_id=second_place_id,
        filename="c.jpg",
    )

    # 4) 첫 사진을 대표사진으로 지정
    cover = client.patch(
        f"/api/v1/trips/{trip_id}", headers=headers, json={"cover_photo_id": photo1["id"]}
    )
    assert cover.status_code == 200, cover.text

    # 5) 방문지에 일기 저장 (SRS 5.2 - 내용 + 날씨)
    diary = client.put(
        f"/api/v1/places/{first_place_id}/diary",
        headers=headers,
        json={"content": "시청 앞에서 커피 한 잔", "weather": "SUNNY"},
    )
    assert diary.status_code == 200, diary.text

    # 6) 상세 화면이 받는 형태 검증 — 이 한 번의 호출로 화면이 다 그려져야 한다
    detail = client.get(f"/api/v1/trips/{trip_id}/detail", headers=headers).json()

    assert detail["country"] == "South Korea"
    assert detail["place_count"] == 2
    assert detail["photo_count"] == 3
    assert detail["cover_photo_id"] == photo1["id"]
    assert detail["thumbnail_url"] is not None
    # 마지막 촬영일 — 프론트의 ON_TRIP 자동 판정 기준
    assert detail["last_taken_at"] == "2026-05-02T09:00:00"

    # 방문지는 경로 순서대로, 사진은 방문지 안에 중첩돼 온다
    assert [p["name"] for p in detail["places"]] == ["서울시청", "남산"]
    assert [p["visit_order"] for p in detail["places"]] == [1, 2]
    assert [p["photo_count"] for p in detail["places"]] == [2, 1]
    assert detail["places"][0]["first_taken_at"] == "2026-05-01T10:30:00"
    assert all(photo["url"] is not None for photo in detail["places"][0]["photos"])

    # 일기는 여행 단위로 함께 내려온다 (방문지별 추가 호출 불필요)
    assert len(detail["diaries"]) == 1
    assert detail["diaries"][0]["place_id"] == first_place_id
    assert detail["diaries"][0]["weather"] == "SUNNY"

    # 7) 지구본 화면 — 같은 데이터가 마커로도 나와야 한다
    globe = client.get("/api/v1/globe", headers=headers).json()
    assert len(globe["trips"]) == 1
    assert [p["name"] for p in globe["trips"][0]["places"]] == ["서울시청", "남산"]


def test_photo_without_gps_is_assigned_when_place_given(client, fake_s3):
    """Place Detail의 '사진 추가'는 GPS가 없어도 그 방문지에 들어가야 한다 (SRS 5.1)."""
    signup(client)
    headers = {"Authorization": f"Bearer {login(client).json()['access_token']}"}
    trip_id = client.post("/api/v1/trips", headers=headers, json={"title": "여행"}).json()["id"]
    place_id = client.post(
        f"/api/v1/trips/{trip_id}/places",
        headers=headers,
        json={"name": "어딘가", "anchor_lat": BASE_LAT, "anchor_lng": BASE_LNG},
    ).json()["id"]

    photo = _presign_put_complete(
        client,
        headers,
        fake_s3,
        lat=None,
        lng=None,
        taken=None,
        place_id=place_id,
        filename="no-exif.jpg",
    )

    assert photo["place_id"] == place_id
    # EXIF가 없으면 촬영일시는 null이다 (SRS 5.1)
    assert photo["taken_at"] is None
    assert photo["latitude"] is None


def test_weather_only_diary_then_content_added(client, fake_s3):
    """날씨만 먼저 저장하고 나중에 본문을 채우는 순서도 동작해야 한다."""
    signup(client)
    headers = {"Authorization": f"Bearer {login(client).json()['access_token']}"}
    trip_id = client.post("/api/v1/trips", headers=headers, json={"title": "여행"}).json()["id"]
    place_id = client.post(
        f"/api/v1/trips/{trip_id}/places",
        headers=headers,
        json={"name": "어딘가", "anchor_lat": BASE_LAT, "anchor_lng": BASE_LNG},
    ).json()["id"]

    first = client.put(
        f"/api/v1/places/{place_id}/diary",
        headers=headers,
        json={"content": "", "weather": "RAINY"},
    )
    assert first.status_code == 200

    second = client.put(
        f"/api/v1/places/{place_id}/diary",
        headers=headers,
        json={"content": "비가 왔다", "weather": "RAINY"},
    )
    assert second.status_code == 200

    # 방문지당 1개이므로 덮어쓰기다 (2개가 생기면 안 된다)
    detail = client.get(f"/api/v1/trips/{trip_id}/detail", headers=headers).json()
    assert len(detail["diaries"]) == 1
    assert detail["diaries"][0]["content"] == "비가 왔다"
