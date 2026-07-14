from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError

KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
KAKAO_USER_ME_URL = "https://kapi.kakao.com/v2/user/me"


@dataclass
class KakaoUserInfo:
    kakao_id: int
    email: str | None
    nickname: str | None


class KakaoOAuthClient(Protocol):
    """테스트에서는 이 인터페이스를 구현한 fake를 주입한다."""

    def get_user_info(self, code: str, redirect_uri: str | None) -> KakaoUserInfo: ...


class KakaoOAuthClientImpl:
    def get_user_info(self, code: str, redirect_uri: str | None) -> KakaoUserInfo:
        settings = get_settings()
        token_res = httpx.post(
            KAKAO_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": settings.kakao_client_id,
                "redirect_uri": redirect_uri or settings.kakao_redirect_uri,
                "code": code,
            },
            timeout=10.0,
        )
        if token_res.status_code != 200:
            raise UnauthorizedError("카카오 인가 코드가 유효하지 않습니다.")
        access_token = token_res.json().get("access_token")
        if not access_token:
            raise UnauthorizedError("카카오 토큰 발급에 실패했습니다.")

        me_res = httpx.get(
            KAKAO_USER_ME_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10.0,
        )
        if me_res.status_code != 200:
            raise UnauthorizedError("카카오 사용자 정보 조회에 실패했습니다.")

        data = me_res.json()
        kakao_account = data.get("kakao_account") or {}
        profile = kakao_account.get("profile") or {}
        return KakaoUserInfo(
            kakao_id=data["id"],
            email=kakao_account.get("email"),
            nickname=profile.get("nickname"),
        )


def get_kakao_client() -> KakaoOAuthClient:
    """FastAPI 의존성. 테스트에서 dependency_overrides로 교체한다."""
    return KakaoOAuthClientImpl()
