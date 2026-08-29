from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from .config import Settings


@dataclass(frozen=True)
class StoredMedia:
    media_id: str
    url: str
    storage_key: str
    backend: str


class MediaStore(Protocol):
    def save(self, content: bytes, mime_type: str) -> StoredMedia: ...

    def read(self, storage_key: str) -> bytes: ...

    def delete(self, storage_key: str) -> None: ...


class LocalMediaStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def save(self, content: bytes, mime_type: str) -> StoredMedia:
        self.root.mkdir(parents=True, exist_ok=True)
        media_id = f"upload_{uuid4().hex[:16]}"
        filename = f"{media_id}{_extension(mime_type)}"
        target = self.root / filename
        target.write_bytes(content)
        return StoredMedia(
            media_id=media_id,
            # Served through the owner-checked API route, never a public static mount.
            url=f"/api/v1/media/{media_id}",
            storage_key=filename,
            backend="local",
        )

    def read(self, storage_key: str) -> bytes:
        return self._target(storage_key).read_bytes()

    def delete(self, storage_key: str) -> None:
        self._target(storage_key).unlink(missing_ok=True)

    def _target(self, storage_key: str) -> Path:
        target = (self.root / storage_key).resolve()
        if not target.is_relative_to(self.root.resolve()):
            raise FileNotFoundError(storage_key)
        return target


class CloudStorageMediaStore:
    def __init__(self, project: str, bucket_name: str) -> None:
        self.project = project
        self.bucket_name = bucket_name
        self._bucket = None

    def save(self, content: bytes, mime_type: str) -> StoredMedia:
        media_id = f"upload_{uuid4().hex[:16]}"
        storage_key = f"uploads/{media_id}{_extension(mime_type)}"
        blob = self._get_bucket().blob(storage_key)
        blob.upload_from_string(content, content_type=mime_type)
        return StoredMedia(
            media_id=media_id,
            url=f"/api/v1/media/{media_id}",
            storage_key=storage_key,
            backend="gcs",
        )

    def read(self, storage_key: str) -> bytes:
        return self._get_bucket().blob(storage_key).download_as_bytes()

    def delete(self, storage_key: str) -> None:
        try:
            self._get_bucket().blob(storage_key).delete()
        except Exception as exc:
            try:
                from google.api_core.exceptions import NotFound
            except ImportError:
                raise exc
            if not isinstance(exc, NotFound):
                raise

    def _get_bucket(self):
        if self._bucket is None:
            try:
                from google.cloud import storage
            except ImportError as exc:
                raise RuntimeError("Install the Google integration: pip install -e '.[google]'") from exc
            self._bucket = storage.Client(project=self.project).bucket(self.bucket_name)
        return self._bucket


def build_media_store(settings: Settings) -> MediaStore:
    if settings.environment == "production" and settings.google_cloud_project and settings.media_bucket:
        return CloudStorageMediaStore(settings.google_cloud_project, settings.media_bucket)
    return LocalMediaStore(settings.uploads_root)


def _extension(mime_type: str) -> str:
    return {"image/png": ".png", "image/webp": ".webp"}.get(mime_type, ".jpg")
