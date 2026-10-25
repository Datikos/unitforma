"""Object storage behind the S3 API, with a local-filesystem backend for tests and dev (plan §4.4).

Keys follow ``t/{tenant_id}/p/{project_id}/...``; access only through presigned URLs issued after
authorization (plan §3.4). The local backend serves files through the API itself.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

from unitforma.core.settings import Settings, get_settings


@dataclass(frozen=True)
class ObjectInfo:
    key: str
    size: int
    content_type: str | None


class Storage(Protocol):
    def presign_put(self, key: str, content_type: str, expires: int = 900) -> str: ...
    def presign_get(self, key: str, expires: int = 900, filename: str | None = None) -> str: ...
    def head(self, key: str) -> ObjectInfo | None: ...
    def get_bytes(self, key: str) -> bytes: ...
    def put_bytes(self, key: str, data: bytes, content_type: str) -> None: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    """Filesystem backend. Presigned URLs are HMAC-signed paths served by ``/internal/files``."""

    def __init__(self, root: Path, secret: str, public_base: str = ""):
        self.root = root
        self.secret = secret.encode()
        self.public_base = public_base.rstrip("/")
        root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root.resolve())):
            raise ValueError("invalid key")
        return p

    def sign(self, method: str, key: str, exp: int) -> str:
        return hmac.new(self.secret, f"{method}:{key}:{exp}".encode(), hashlib.sha256).hexdigest()

    def verify(self, method: str, key: str, exp: int, sig: str) -> bool:
        return exp > int(time.time()) and hmac.compare_digest(self.sign(method, key, exp), sig)

    def presign_put(self, key: str, content_type: str, expires: int = 900) -> str:
        exp = int(time.time()) + expires
        sig = self.sign("PUT", key, exp)
        return f"{self.public_base}/internal/files/{quote(key)}?method=PUT&exp={exp}&sig={sig}"

    def presign_get(self, key: str, expires: int = 900, filename: str | None = None) -> str:
        exp = int(time.time()) + expires
        sig = self.sign("GET", key, exp)
        return f"{self.public_base}/internal/files/{quote(key)}?method=GET&exp={exp}&sig={sig}"

    def head(self, key: str) -> ObjectInfo | None:
        p = self._path(key)
        if not p.is_file():
            return None
        return ObjectInfo(key=key, size=p.stat().st_size, content_type=None)

    def get_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def delete(self, key: str) -> None:
        p = self._path(key)
        if p.is_file():
            p.unlink()
        elif p.is_dir():
            shutil.rmtree(p)


class S3Storage:
    def __init__(self, settings: Settings):
        import boto3
        from botocore.config import Config

        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        # Browsers must reach the presigned URL through the public host, not the Docker name.
        self.public_client = (
            boto3.client(
                "s3",
                endpoint_url=settings.s3_public_url,
                region_name=settings.s3_region,
                aws_access_key_id=settings.s3_access_key,
                aws_secret_access_key=settings.s3_secret_key,
                config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
            )
            if settings.s3_public_url
            else self.client
        )

    def presign_put(self, key: str, content_type: str, expires: int = 900) -> str:
        return self.public_client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expires,
        )

    def presign_get(self, key: str, expires: int = 900, filename: str | None = None) -> str:
        params = {"Bucket": self.bucket, "Key": key}
        if filename:
            params["ResponseContentDisposition"] = f'inline; filename="{filename}"'
        return self.public_client.generate_presigned_url(
            "get_object", Params=params, ExpiresIn=expires
        )

    def head(self, key: str) -> ObjectInfo | None:
        try:
            r = self.client.head_object(Bucket=self.bucket, Key=key)
        except self.client.exceptions.ClientError:
            return None
        return ObjectInfo(key=key, size=r["ContentLength"], content_type=r.get("ContentType"))

    def get_bytes(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        s = get_settings()
        if s.storage_backend == "local":
            _storage = LocalStorage(
                Path(s.storage_local_root), s.app_session_key, s.storage_public_base
            )
        else:
            _storage = S3Storage(s)
    return _storage


def reset_storage() -> None:
    global _storage
    _storage = None


def object_key(tenant_id, project_id, *parts: str) -> str:
    safe = [quote(str(p), safe="._-") for p in parts]
    return "/".join(["t", str(tenant_id), "p", str(project_id), *safe])


def safe_filename(name: str) -> str:
    base = os.path.basename(name).strip() or "file"
    return "".join(c if c.isalnum() or c in "._- ()" else "_" for c in base)[:200]
