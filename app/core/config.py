from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://travelog:travelog@localhost:5432/travelog"

    jwt_secret_key: str = "change-me-in-local-env"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14

    aws_region: str = "ap-northeast-2"
    s3_bucket_name: str = ""
    s3_presign_expire_seconds: int = 3600

    # 클라이언트가 업로드 시 사진을 방문지로 묶는 임계값(300m)과 맞춘다.
    # 값이 다르면 같은 클러스터의 사진이 서버에서 미분류로 떨어진다.
    default_place_radius_m: int = 300


@lru_cache
def get_settings() -> Settings:
    return Settings()
