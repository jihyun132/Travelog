SIGNUP_PAYLOAD = {
    "email": "traveler@example.com",
    "password": "password123",
    "name": "여행자",
    "birth_date": "1999-03-01",
}


def signup(client, payload=None):
    return client.post("/api/v1/auth/signup", json=payload or SIGNUP_PAYLOAD)


def login(client, email=SIGNUP_PAYLOAD["email"], password=SIGNUP_PAYLOAD["password"]):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


# ── 회원가입 ──────────────────────────────────────────────


def test_signup_success(client):
    res = signup(client)

    assert res.status_code == 201
    body = res.json()
    assert body["email"] == SIGNUP_PAYLOAD["email"]
    assert body["name"] == SIGNUP_PAYLOAD["name"]
    assert "password" not in body and "password_hash" not in body


def test_signup_duplicate_email_returns_409(client):
    signup(client)
    res = signup(client)

    assert res.status_code == 409
    body = res.json()
    assert body["code"] == "CONFLICT"
    assert "이미 가입된 이메일" in body["message"]


def test_signup_invalid_email_returns_422(client):
    res = signup(client, {**SIGNUP_PAYLOAD, "email": "not-an-email"})

    assert res.status_code == 422


# ── 로그인 ────────────────────────────────────────────────


def test_login_success_returns_tokens(client):
    signup(client)
    res = login(client)

    assert res.status_code == 200
    body = res.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == SIGNUP_PAYLOAD["email"]


def test_login_wrong_password_returns_401(client):
    signup(client)
    res = login(client, password="wrong-password")

    assert res.status_code == 401
    assert res.json()["code"] == "UNAUTHORIZED"


def test_login_unknown_email_returns_401(client):
    res = login(client, email="nobody@example.com")

    assert res.status_code == 401


# ── 인증 의존성 (/users/me) ───────────────────────────────


def test_me_with_valid_token(client):
    signup(client)
    tokens = login(client).json()

    res = client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )

    assert res.status_code == 200
    assert res.json()["email"] == SIGNUP_PAYLOAD["email"]


def test_me_without_token_returns_401(client):
    res = client.get("/api/v1/users/me")

    assert res.status_code == 401


def test_me_with_garbage_token_returns_401(client):
    res = client.get("/api/v1/users/me", headers={"Authorization": "Bearer garbage"})

    assert res.status_code == 401


# ── Refresh (rotation) ───────────────────────────────────


def test_refresh_returns_new_tokens_and_revokes_old(client):
    signup(client)
    old_refresh = login(client).json()["refresh_token"]

    res = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert res.status_code == 200
    assert res.json()["access_token"]

    # 한 번 사용한 refresh 토큰은 재사용 불가 (rotation)
    res2 = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert res2.status_code == 401


def test_refresh_with_invalid_token_returns_401(client):
    res = client.post("/api/v1/auth/refresh", json={"refresh_token": "garbage"})

    assert res.status_code == 401


# ── 로그아웃 ──────────────────────────────────────────────


def test_logout_revokes_refresh_token(client):
    signup(client)
    tokens = login(client).json()

    res = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert res.status_code == 204

    res2 = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert res2.status_code == 401


def test_logout_without_token_returns_401(client):
    res = client.post("/api/v1/auth/logout", json={"refresh_token": "anything"})

    assert res.status_code == 401


# ── 아이디(이메일) 찾기 ──────────────────────────────────


def test_find_email_returns_masked_email(client):
    signup(client)

    res = client.post(
        "/api/v1/auth/find-email",
        json={"name": SIGNUP_PAYLOAD["name"], "birth_date": SIGNUP_PAYLOAD["birth_date"]},
    )

    assert res.status_code == 200
    # traveler@example.com → tr******@example.com
    assert res.json()["email"] == "tr******@example.com"


def test_find_email_with_wrong_birth_date_returns_404(client):
    signup(client)

    res = client.post(
        "/api/v1/auth/find-email",
        json={"name": SIGNUP_PAYLOAD["name"], "birth_date": "2000-01-01"},
    )

    assert res.status_code == 404
