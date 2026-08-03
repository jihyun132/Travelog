from functools import lru_cache
from typing import Protocol

import boto3

from app.core.config import get_settings

# S3 DeleteObjects API 1회 요청당 객체 수 상한
_DELETE_BATCH_SIZE = 1000


class S3Storage(Protocol):
    """S3 접근 인터페이스. 테스트에서는 fake 구현을 주입한다."""

    def presign_put(self, key: str, content_type: str) -> str: ...

    def presign_get(self, key: str) -> str: ...

    def get_object(self, key: str) -> bytes:
        """객체가 없으면 FileNotFoundError."""
        ...

    def delete_objects(self, keys: list[str]) -> None:
        """여러 객체를 일괄 삭제한다. 존재하지 않는 키는 무시된다."""
        ...


class Boto3S3Storage:
    def __init__(self, bucket: str, region: str, expire_seconds: int):
        self._bucket = bucket
        self._expire = expire_seconds
        self._client = boto3.client("s3", region_name=region)

    def presign_put(self, key: str, content_type: str) -> str:
        return self._client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self._bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=self._expire,
        )

    def presign_get(self, key: str) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=self._expire,
        )

    def get_object(self, key: str) -> bytes:
        try:
            return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        except self._client.exceptions.NoSuchKey:
            raise FileNotFoundError(key) from None

    def delete_objects(self, keys: list[str]) -> None:
        # DeleteObjects API는 1회 최대 1000개까지만 받는다.
        for start in range(0, len(keys), _DELETE_BATCH_SIZE):
            batch = keys[start : start + _DELETE_BATCH_SIZE]
            self._client.delete_objects(
                Bucket=self._bucket,
                Delete={"Objects": [{"Key": key} for key in batch], "Quiet": True},
            )


@lru_cache
def get_s3_storage() -> S3Storage:
    settings = get_settings()
    return Boto3S3Storage(
        settings.s3_bucket_name, settings.aws_region, settings.s3_presign_expire_seconds
    )
