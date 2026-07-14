from io import BytesIO

from PIL import Image

from tests.test_auth import SIGNUP_PAYLOAD, login, signup

GPS_IFD = 0x8825
EXIF_IFD = 0x8769
TAG_DATETIME_ORIGINAL = 0x9003

# 37°33'36"N 126°58'12"E = (37.56, 126.97) — 서울 시청 인근
SEOUL_GPS = {1: "N", 2: (37.0, 33.0, 36.0), 3: "E", 4: (126.0, 58.0, 12.0)}


def make_jpeg(gps: dict | None = SEOUL_GPS, taken: str | None = "2026:05:01 10:30:00") -> bytes:
    image = Image.new("RGB", (8, 8), "white")
    exif = Image.Exif()
    if gps is not None:
        exif[GPS_IFD] = gps
    if taken is not None:
        exif[EXIF_IFD] = {TAG_DATETIME_ORIGINAL: taken}
    buf = BytesIO()
    image.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def auth_headers(client) -> dict:
    signup(client)
    token = login(client).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def upload(client, headers, data: bytes, filename: str = "photo.jpg"):
    return client.post(
        "/api/v1/photo-locations",
        headers=headers,
        files={"file": (filename, data, "image/jpeg")},
    )


# ── 업로드(파싱·저장) ─────────────────────────────────────


def test_upload_extracts_gps_and_taken_at(client):
    headers = auth_headers(client)

    res = upload(client, headers, make_jpeg())

    assert res.status_code == 201
    body = res.json()
    assert body["filename"] == "photo.jpg"
    assert abs(body["latitude"] - 37.56) < 1e-6
    assert abs(body["longitude"] - 126.97) < 1e-6
    assert body["taken_at"] == "2026-05-01T10:30:00"


def test_upload_south_west_hemisphere_is_negative(client):
    headers = auth_headers(client)
    gps = {1: "S", 2: (33.0, 52.0, 12.0), 3: "W", 4: (70.0, 30.0, 0.0)}

    res = upload(client, headers, make_jpeg(gps=gps))

    assert res.status_code == 201
    body = res.json()
    assert body["latitude"] < 0
    assert body["longitude"] < 0


def test_upload_without_taken_at_returns_null(client):
    headers = auth_headers(client)

    res = upload(client, headers, make_jpeg(taken=None))

    assert res.status_code == 201
    assert res.json()["taken_at"] is None


def test_upload_without_gps_returns_400(client):
    headers = auth_headers(client)

    res = upload(client, headers, make_jpeg(gps=None))

    assert res.status_code == 400
    body = res.json()
    assert body["code"] == "INVALID_PHOTO"
    assert "GPS" in body["message"]


def test_upload_non_image_returns_400(client):
    headers = auth_headers(client)

    res = upload(client, headers, b"not an image", filename="note.txt")

    assert res.status_code == 400
    assert res.json()["code"] == "INVALID_PHOTO"


def test_upload_without_auth_returns_401(client):
    res = upload(client, headers={}, data=make_jpeg())

    assert res.status_code == 401


# ── 전체 좌표 조회 ────────────────────────────────────────


def test_list_returns_own_locations(client):
    headers = auth_headers(client)
    upload(client, headers, make_jpeg())
    upload(client, headers, make_jpeg(), filename="photo2.jpg")

    res = client.get("/api/v1/photo-locations", headers=headers)

    assert res.status_code == 200
    body = res.json()
    assert len(body) == 2
    assert [loc["filename"] for loc in body] == ["photo.jpg", "photo2.jpg"]


def test_list_excludes_other_users_locations(client):
    headers = auth_headers(client)
    upload(client, headers, make_jpeg())

    other_payload = {**SIGNUP_PAYLOAD, "email": "other@example.com"}
    signup(client, other_payload)
    other_token = login(client, email=other_payload["email"]).json()["access_token"]
    other_headers = {"Authorization": f"Bearer {other_token}"}

    res = client.get("/api/v1/photo-locations", headers=other_headers)

    assert res.status_code == 200
    assert res.json() == []


def test_list_without_auth_returns_401(client):
    res = client.get("/api/v1/photo-locations")

    assert res.status_code == 401
