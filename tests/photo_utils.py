"""사진 관련 테스트 공용 헬퍼."""

from io import BytesIO

from PIL import Image

from tests.test_auth import SIGNUP_PAYLOAD, login, signup

GPS_IFD = 0x8825
EXIF_IFD = 0x8769
TAG_DATETIME_ORIGINAL = 0x9003

# 기준점: 서울시청 인근
BASE_LAT = 37.5665
BASE_LNG = 126.978

# 위도 1도 ≈ 111,320m — 미터 단위 오프셋을 위도 차이로 환산할 때 사용
METERS_PER_DEG_LAT = 111_320


def offset_lat(lat: float, meters: float) -> float:
    """기준 위도에서 북쪽으로 meters만큼 이동한 위도."""
    return lat + meters / METERS_PER_DEG_LAT


def _to_dms(value: float) -> tuple[float, float, float]:
    value = abs(value)
    degrees = int(value)
    minutes = int((value - degrees) * 60)
    seconds = (value - degrees - minutes / 60) * 3600
    return (float(degrees), float(minutes), seconds)


def make_jpeg(
    lat: float | None = BASE_LAT,
    lng: float | None = BASE_LNG,
    taken: str | None = "2026:05:01 10:30:00",
) -> bytes:
    image = Image.new("RGB", (8, 8), "white")
    exif = Image.Exif()
    if lat is not None and lng is not None:
        exif[GPS_IFD] = {
            1: "S" if lat < 0 else "N",
            2: _to_dms(lat),
            3: "W" if lng < 0 else "E",
            4: _to_dms(lng),
        }
    if taken is not None:
        exif[EXIF_IFD] = {TAG_DATETIME_ORIGINAL: taken}
    buf = BytesIO()
    image.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def auth_headers(client, email: str | None = None) -> dict:
    payload = SIGNUP_PAYLOAD if email is None else {**SIGNUP_PAYLOAD, "email": email}
    signup(client, payload)
    token = login(client, email=payload["email"]).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_trip(client, headers, title="오사카 여행", **fields) -> int:
    """여행을 만들고 id를 반환한다. 방문지는 여행에 종속되므로 대부분의 테스트가 먼저 호출한다."""
    res = client.post("/api/v1/trips", headers=headers, json={"title": title, **fields})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def create_place(
    client,
    headers,
    trip_id: int | None = None,
    *,
    name="서울시청",
    lat=BASE_LAT,
    lng=BASE_LNG,
    radius=None,
):
    """방문지 생성 응답을 반환한다. trip_id를 주지 않으면 여행을 새로 만든다."""
    if trip_id is None:
        trip_id = create_trip(client, headers)
    payload = {"name": name, "anchor_lat": lat, "anchor_lng": lng}
    if radius is not None:
        payload["radius_m"] = radius
    return client.post(f"/api/v1/trips/{trip_id}/places", headers=headers, json=payload)


def upload_photo(
    client,
    headers: dict,
    fake_s3,
    *,
    lat: float | None = BASE_LAT,
    lng: float | None = BASE_LNG,
    taken: str | None = "2026:05:01 10:30:00",
    filename: str = "photo.jpg",
    data: bytes | None = None,
    place_id: int | None = None,
):
    """presign → fake S3에 바이트 저장 → complete까지 수행하고 complete 응답을 반환.

    place_id를 주면 반경 자동 배정 대신 그 방문지로 확정 배정한다.
    """
    presign = client.post(
        "/api/v1/photos/presign",
        headers=headers,
        json={"filename": filename, "content_type": "image/jpeg"},
    )
    assert presign.status_code == 201, presign.text
    body = presign.json()
    fake_s3.objects[body["s3_key"]] = data if data is not None else make_jpeg(lat, lng, taken)
    return client.post(
        f"/api/v1/photos/{body['photo_id']}/complete",
        headers=headers,
        json={"place_id": place_id},
    )
