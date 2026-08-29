from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path


def project_root() -> Path:
    explicit = os.getenv("REALITYDIFF_ROOT")
    if explicit:
        return Path(explicit).expanduser().resolve()
    source_root = Path(__file__).resolve().parents[2]
    working_root = Path.cwd().resolve()
    for candidate in (working_root, source_root):
        if (candidate / "web" / "fixtures" / "demo.json").is_file():
            return candidate
    return source_root


@dataclass(frozen=True)
class Settings:
    environment: str = field(default_factory=lambda: os.getenv("REALITYDIFF_ENV", "demo"))
    google_cloud_project: str | None = field(default_factory=lambda: os.getenv("GOOGLE_CLOUD_PROJECT"))
    google_cloud_location: str = field(
        default_factory=lambda: os.getenv("GOOGLE_CLOUD_LOCATION", "global")
    )
    gemini_model: str = field(
        default_factory=lambda: os.getenv("REALITYDIFF_GEMINI_MODEL", "gemini-3.7-flash")
    )
    triage_model: str = field(
        default_factory=lambda: os.getenv(
            "REALITYDIFF_TRIAGE_MODEL", "gemini-3.5-flash-lite"
        )
    )
    embedding_model: str = field(
        default_factory=lambda: os.getenv("REALITYDIFF_EMBEDDING_MODEL", "gemini-embedding-2")
    )
    gemini_api_key: str | None = field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    )
    media_bucket: str | None = field(default_factory=lambda: os.getenv("REALITYDIFF_MEDIA_BUCKET"))
    pubsub_topic: str = field(
        default_factory=lambda: os.getenv(
            "REALITYDIFF_PUBSUB_TOPIC", "reality-diff-ingestion"
        )
    )
    # Shared secret that gates the Pub/Sub push endpoint for the asynchronous
    # state-construction stage. Unset locally (the stage is disabled); Terraform sets it
    # in production and puts the same value in the push subscription URL.
    pipeline_token: str | None = field(
        default_factory=lambda: os.getenv("REALITYDIFF_PIPELINE_TOKEN")
    )
    uploads_root: Path = field(
        default_factory=lambda: Path(
            os.getenv("REALITYDIFF_UPLOADS_ROOT", str(project_root() / "var" / "uploads"))
        )
    )
    max_upload_bytes: int = field(
        default_factory=lambda: int(os.getenv("REALITYDIFF_MAX_UPLOAD_BYTES", str(12 * 1024 * 1024)))
    )
    state_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("REALITYDIFF_STATE_PATH", str(project_root() / "var" / "demo-state.json"))
        )
    )
    fixture_path: Path = field(
        default_factory=lambda: project_root() / "web" / "fixtures" / "demo.json"
    )
    web_root: Path = field(default_factory=lambda: project_root() / "web")

    @property
    def live_model_enabled(self) -> bool:
        return self.environment == "production" and bool(
            self.google_cloud_project or self.gemini_api_key
        )

    @property
    def vertex_ai_enabled(self) -> bool:
        return self.live_model_enabled and not self.gemini_api_key


settings = Settings()
