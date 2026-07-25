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

    default_group_radius_m: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
