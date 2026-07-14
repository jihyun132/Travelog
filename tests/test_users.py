from app.main import app
from app.services.kakao_client import KakaoUserInfo, get_kakao_client

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


def test_withdraw_success_hard_deletes_and_revokes_tokens(client):
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


def test_withdraw_wrong_password_returns_401_and_keeps_account(client):
    tokens = _signup_and_login(client)

    res = _withdraw(client, tokens["access_token"], password="wrong-password")
    assert res.status_code == 401
    assert "비밀번호" in res.json()["message"]

    # 계정이 그대로 남아 있어야 한다
    res2 = client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert res2.status_code == 200


def test_withdraw_missing_password_returns_401(client):
    tokens = _signup_and_login(client)

    res = _withdraw(client, tokens["access_token"], password=None)
    assert res.status_code == 401


def test_withdraw_without_auth_returns_401(client):
    res = client.request("DELETE", "/api/v1/users/me", json={"password": "whatever"})

    assert res.status_code == 401


def test_withdraw_kakao_only_user_without_password(client):
    app.dependency_overrides[get_kakao_client] = lambda: _FakeKakao(
        KakaoUserInfo(kakao_id=777, email="kakao-only@example.com", nickname="카카오탈퇴")
    )
    try:
        tokens = client.post("/api/v1/auth/kakao", json={"code": "dummy"}).json()
    finally:
        app.dependency_overrides.pop(get_kakao_client, None)

    res = _withdraw(client, tokens["access_token"], password=None)

    assert res.status_code == 204


class _FakeKakao:
    def __init__(self, info):
        self.info = info

    def get_user_info(self, code, redirect_uri):
        return self.info
