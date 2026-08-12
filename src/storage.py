"""Object storage abstraction (Phase C) — local disk or S3-compatible.

Usage:
    from src.storage import get_storage
    store = get_storage()
    key = store.put_file(local_path, key="uploads/a.dxf")
    path = store.fetch_to_local(key)
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


class StorageBackend(Protocol):
    def put_file(self, local_path: str, key: str, content_type: str = "") -> str: ...
    def fetch_to_local(self, key: str, dest_path: str | None = None) -> str: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
    def url(self, key: str, expires_in: int = 3600) -> str: ...


class LocalStorage:
    def __init__(self, root: str | None = None):
        if root is None:
            try:
                from src.workspace import get_project_root
                root = os.path.join(get_project_root(), "uploads")
            except Exception:
                root = "uploads"
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = key.lstrip("/").replace("..", "_")
        return self.root / safe

    def put_file(self, local_path: str, key: str, content_type: str = "") -> str:
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, dest)
        logger.info("LocalStorage put %s → %s", local_path, dest)
        return key

    def fetch_to_local(self, key: str, dest_path: str | None = None) -> str:
        src = self._path(key)
        if not src.exists():
            raise FileNotFoundError(f"LocalStorage: không tìm thấy key={key}")
        if dest_path is None:
            return str(src)
        Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest_path)
        return dest_path

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            p.unlink()

    def url(self, key: str, expires_in: int = 3600) -> str:
        return f"file://{self._path(key)}"


class S3Storage:
    def __init__(self, bucket: str, *, endpoint_url: str = "", access_key: str = "", secret_key: str = "", region: str = "ap-southeast-1", prefix: str = "mep-agents/"):
        import boto3
        from botocore.client import Config

        self.bucket = bucket
        self.prefix = prefix.rstrip("/") + "/" if prefix else ""
        kwargs: dict = {"region_name": region}
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        if access_key and secret_key:
            kwargs["aws_access_key_id"] = access_key
            kwargs["aws_secret_access_key"] = secret_key
        self.client = boto3.client("s3", config=Config(signature_version="s3v4"), **kwargs)
        self._local_cache = Path(os.environ.get("S3_LOCAL_CACHE", "/tmp/mep_s3_cache"))
        self._local_cache.mkdir(parents=True, exist_ok=True)

    def _full_key(self, key: str) -> str:
        key = key.lstrip("/")
        if self.prefix and not key.startswith(self.prefix):
            return self.prefix + key
        return key

    def put_file(self, local_path: str, key: str, content_type: str = "") -> str:
        full = self._full_key(key)
        extra = {}
        if content_type:
            extra["ContentType"] = content_type
        self.client.upload_file(local_path, self.bucket, full, ExtraArgs=extra or None)
        logger.info("S3 put %s → s3://%s/%s", local_path, self.bucket, full)
        return key

    def fetch_to_local(self, key: str, dest_path: str | None = None) -> str:
        full = self._full_key(key)
        if dest_path is None:
            dest_path = str(self._local_cache / full.replace("/", "_"))
        Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(self.bucket, full, dest_path)
        return dest_path

    def exists(self, key: str) -> bool:
        full = self._full_key(key)
        try:
            self.client.head_object(Bucket=self.bucket, Key=full)
            return True
        except Exception:
            return False

    def delete(self, key: str) -> None:
        full = self._full_key(key)
        self.client.delete_object(Bucket=self.bucket, Key=full)

    def url(self, key: str, expires_in: int = 3600) -> str:
        full = self._full_key(key)
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": full},
            ExpiresIn=expires_in,
        )


_STORAGE = None


def get_storage():
    global _STORAGE
    if _STORAGE is not None:
        return _STORAGE
    try:
        from src.config import settings
        bucket = (getattr(settings, "s3_bucket", None) or os.environ.get("S3_BUCKET", "") or "").strip()
        if bucket:
            _STORAGE = S3Storage(
                bucket,
                endpoint_url=getattr(settings, "s3_endpoint_url", "") or os.environ.get("S3_ENDPOINT_URL", ""),
                access_key=getattr(settings, "s3_access_key", "") or os.environ.get("S3_ACCESS_KEY", ""),
                secret_key=getattr(settings, "s3_secret_key", "") or os.environ.get("S3_SECRET_KEY", ""),
                region=getattr(settings, "s3_region", "") or os.environ.get("S3_REGION", "ap-southeast-1"),
                prefix=getattr(settings, "s3_prefix", "") or os.environ.get("S3_PREFIX", "mep-agents/"),
            )
            logger.info("Using S3Storage bucket=%s", bucket)
            return _STORAGE
    except Exception as e:
        logger.warning("S3 init failed (%s) — fallback LocalStorage", e)
    _STORAGE = LocalStorage()
    return _STORAGE


def reset_storage_for_tests() -> None:
    global _STORAGE
    _STORAGE = None
