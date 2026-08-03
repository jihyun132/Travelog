from tests.photo_utils import upload_photo

SIGNUP_PAYLOAD = {
    "email": "withdraw@example.com",
    "password": "password123",
    "name": "탈퇴테스트",
}


def _signup_and_login(client):
    client.post("/api/v1/auth/signup", json=SIGNUP_PAYLOAD)
    res = client.post(
        "/api/v1/auth/login",
        json={"email": SIGNUP_PAYLOAD["email"], "password": SIGNUP_PAYLOAD["password"]},
    )
    return res.json()


def _withdraw(client, access_token, password=None):
    return client.request(
        "DELETE",
        "/api/v1/users/me",
        json={"password": password},
        headers={"Authorization": f"Bearer {access_token}"},
    )


# ── 회원 탈퇴 ─────────────────────────────────────────────


def test_withdraw_success_hard_deletes_and_revokes_tokens(client, fake_s3):
    tokens = _signup_and_login(client)

    res = _withdraw(client, tokens["access_token"], password=SIGNUP_PAYLOAD["password"])
    assert res.status_code == 204

    # 하드 삭제 확인: 같은 계정으로 로그인 불가
    res2 = client.post(
        "/api/v1/auth/login",
        json={"email": SIGNUP_PAYLOAD["email"], "password": SIGNUP_PAYLOAD["password"]},
    )
    assert res2.status_code == 401

    # 모든 Refresh 토큰 무효화 확인 (CASCADE)
    res3 = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert res3.status_code == 401

    # 같은 이메일로 재가입 가능 (하드 삭제이므로 409가 아님)
    res4 = client.post("/api/v1/auth/signup", json=SIGNUP_PAYLOAD)
    assert res4.status_code == 201


def test_withdraw_wrong_password_returns_401_and_keeps_account(client, fake_s3):
    tokens = _signup_and_login(client)

    res = _withdraw(client, tokens["access_token"], password="wrong-password")
    assert res.status_code == 401
    assert "비밀번호" in res.json()["message"]

    # 계정이 그대로 남아 있어야 한다
    res2 = client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert res2.status_code == 200


def test_withdraw_missing_password_returns_401(client, fake_s3):
    tokens = _signup_and_login(client)

    res = _withdraw(client, tokens["access_token"], password=None)
    assert res.status_code == 401


def test_withdraw_without_auth_returns_401(client):
    res = client.request("DELETE", "/api/v1/users/me", json={"password": "whatever"})

    assert res.status_code == 401


# ── 탈퇴 시 S3 원본 삭제 (SRS 2.1.2) ──────────────────────


def test_withdraw_deletes_s3_objects(client, fake_s3):
    tokens = _signup_and_login(client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    upload_photo(client, headers, fake_s3)
    assert len(fake_s3.objects) == 1

    res = _withdraw(client, tokens["access_token"], password=SIGNUP_PAYLOAD["password"])

    assert res.status_code == 204
    assert fake_s3.objects == {}


def test_withdraw_deletes_pending_upload_objects(client, fake_s3):
    """presign만 받고 complete하지 않은 사진도 S3에서 지워져야 한다."""
    tokens = _signup_and_login(client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    presign = client.post(
        "/api/v1/photos/presign",
        headers=headers,
        json={"filename": "pending.jpg", "content_type": "image/jpeg"},
    )
    fake_s3.objects[presign.json()["s3_key"]] = b"uploaded but never completed"

    res = _withdraw(client, tokens["access_token"], password=SIGNUP_PAYLOAD["password"])

    assert res.status_code == 204
    assert fake_s3.objects == {}


def test_withdraw_keeps_other_users_objects(client, fake_s3):
    tokens = _signup_and_login(client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    upload_photo(client, headers, fake_s3)

    other = client.post(
        "/api/v1/auth/signup", json={**SIGNUP_PAYLOAD, "email": "keeper@example.com"}
    )
    assert other.status_code == 201
    other_login = client.post(
        "/api/v1/auth/login",
        json={"email": "keeper@example.com", "password": SIGNUP_PAYLOAD["password"]},
    ).json()
    other_headers = {"Authorization": f"Bearer {other_login['access_token']}"}
    kept = upload_photo(client, other_headers, fake_s3, filename="keep.jpg")
    assert kept.status_code == 200

    res = _withdraw(client, tokens["access_token"], password=SIGNUP_PAYLOAD["password"])

    assert res.status_code == 204
    remaining = list(fake_s3.objects)
    assert len(remaining) == 1
    assert remaining[0].startswith(f"users/{other_login['user']['id']}/")
