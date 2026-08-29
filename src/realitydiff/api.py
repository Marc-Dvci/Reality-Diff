from __future__ import annotations

import asyncio
import secrets
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError

from . import __version__
from .cloud import build_event_publisher, build_state_backend
from .config import settings
from .live_reasoner import GeminiTemporalReasoner
from .models import AskRequest, CorrectionRequest, IngestionRequest
from .orchestrator import AdkOrchestrator
from .pipeline import GeminiMediaAnalyzer
from .repository import WorldRepository
from .storage import build_media_store
from .temporal import TemporalReasoner
from .worker import build_consolidator, decode_pubsub_event


repository = WorldRepository(
    settings.fixture_path,
    settings.state_path,
    cloud_state=build_state_backend(settings),
)
reasoner = TemporalReasoner(repository)
analyzer = GeminiMediaAnalyzer(settings)
live_reasoner = GeminiTemporalReasoner(repository, analyzer)
orchestrator = AdkOrchestrator(repository, settings) if settings.live_model_enabled else None
media_store = build_media_store(settings)
event_publisher = build_event_publisher(settings)
consolidator = build_consolidator(repository)
app = FastAPI(
    title="Reality Diff API",
    description="Evidence-linked temporal reasoning over photo history.",
    version=__version__,
)

OWNER_COOKIE = "rd_owner"


def resolve_owner(request: Request, response: Response) -> str:
    """Anonymous per-browser identity for private uploads. No account required.

    The public service is open to all, so every upload, gallery view, retrieval, and
    deletion is scoped to a random owner token carried in an HttpOnly cookie. One visitor
    can never see, retrieve, or delete another visitor's photos.
    """
    owner = request.cookies.get(OWNER_COOKIE)
    if not owner:
        owner = secrets.token_urlsafe(24)
        response.set_cookie(
            OWNER_COOKIE,
            owner,
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            samesite="lax",
            secure=request.url.scheme == "https",
            path="/",
        )
    return owner


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "reality-diff-api",
        "version": __version__,
        "mode": settings.environment,
        "model": settings.gemini_model,
        "triage_model": settings.triage_model,
        "embedding_model": settings.embedding_model,
        "live_models": settings.live_model_enabled,
        "google_cloud_project": settings.google_cloud_project,
        "google_cloud_location": settings.google_cloud_location,
    }


@app.get("/ready")
def ready() -> JSONResponse:
    checks = {
        "fixture": settings.fixture_path.is_file(),
        "web": (settings.web_root / "index.html").is_file(),
    }
    ready_state = all(checks.values())
    return JSONResponse(
        status_code=200 if ready_state else 503,
        content={"status": "ready" if ready_state else "not_ready", "checks": checks},
    )


@app.get("/api/v1/bootstrap")
def bootstrap(owner: str = Depends(resolve_owner)) -> dict[str, object]:
    return repository.bootstrap(owner)


@app.get("/api/v1/subjects")
def subjects() -> list[dict[str, object]]:
    return repository.subjects()


@app.get("/api/v1/subjects/{subject_id}")
def subject(subject_id: str) -> dict[str, object]:
    value = repository.subject(subject_id)
    if value is None:
        raise HTTPException(status_code=404, detail="subject not found")
    return value


@app.post("/api/v1/ask")
async def ask(request: AskRequest, owner: str = Depends(resolve_owner)) -> dict[str, object]:
    # The owner is taken from the cookie, never from the body: a visitor can only ever
    # reason over their own uploads, regardless of what the request claims.
    request.owner_id = owner
    # Live deployments route the conversation through the Google ADK partner, which owns
    # tool choice, clarification, and multi-turn state. It falls back to the direct pipeline
    # so the offline demo and any orchestration hiccup still return a grounded answer.
    if orchestrator is not None:
        orchestrated = await orchestrator.answer(request)
        if orchestrated is not None:
            return orchestrated.model_dump()
    deterministic = reasoner.answer(request)
    if deterministic.status != "not_found" or not settings.live_model_enabled:
        return deterministic.model_dump()
    try:
        live_answer = await asyncio.to_thread(live_reasoner.answer, request)
    except Exception:
        live_answer = None
    return (live_answer or deterministic).model_dump()


@app.post("/api/v1/corrections", status_code=201)
def remember_correction(
    request: CorrectionRequest, owner: str = Depends(resolve_owner)
) -> dict[str, object]:
    request.owner_id = owner
    stored = repository.remember(request).model_dump()
    stored.pop("owner_id", None)
    return stored


@app.get("/api/v1/corrections")
def corrections(
    conversation_id: str | None = None, owner: str = Depends(resolve_owner)
) -> list[dict[str, object]]:
    return repository.corrections(conversation_id, owner)


@app.post("/api/v1/ingestion-runs", status_code=202)
def create_ingestion_run(request: IngestionRequest) -> dict[str, object]:
    # The judge dataset is already indexed. This deterministic run exposes the
    # same state transitions as the Pub/Sub workers without claiming a live model
    # call occurred in demo mode.
    duplicates = max(1, round(request.discovered * 0.11)) if request.discovered else 0
    useful = max(0, round((request.discovered - duplicates) * 0.72))
    run = {
        "id": f"ing_{uuid4().hex[:10]}",
        "source": request.source,
        "status": "completed",
        "started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "discovered": request.discovered,
        "deduplicated": duplicates,
        "indexed": request.discovered - duplicates,
        "physical_state_useful": useful,
        "subjects_updated": min(3, useful),
        "events_proposed": min(4, max(0, useful // 3)),
        "transport": "recorded_demo",
    }
    return repository.add_ingestion_run(run)


@app.post("/api/v1/media/analyze", status_code=201)
async def analyze_media(
    files: list[UploadFile] = File(...),
    source: str = Form(default="web_upload"),
    owner: str = Depends(resolve_owner),
) -> dict[str, object]:
    if source not in {"android_mediastore", "android_picker", "web_folder", "web_upload"}:
        raise HTTPException(status_code=422, detail="unsupported media source")
    if not files or len(files) > 12:
        raise HTTPException(status_code=422, detail="upload between 1 and 12 photos at a time")

    prepared: list[tuple[UploadFile, bytes, str, str, str, str]] = []
    for upload in files:
        content = await upload.read(settings.max_upload_bytes + 1)
        if len(content) > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail=f"{upload.filename or 'photo'} is too large")
        inspected = _inspect_image(content)
        if inspected is None:
            raise HTTPException(
                status_code=415,
                detail=f"{upload.filename or 'file'} is not a supported JPEG, PNG, or WebP image",
            )
        mime_type, captured_at, capture_time_source = inspected
        prepared.append(
            (
                upload,
                content,
                mime_type,
                captured_at,
                capture_time_source,
                sha256(content).hexdigest(),
            )
        )

    items: list[dict[str, object]] = []
    duplicates: list[dict[str, str]] = []
    failures = 0
    event_failures = 0
    for upload, content, mime_type, captured_at, capture_time_source, digest in prepared:
        existing = repository.upload_by_hash(digest, owner)
        if existing is not None:
            duplicates.append(
                {
                    "filename": upload.filename or "photo",
                    "existing_media_id": str(existing["id"]),
                }
            )
            continue

        stored = await asyncio.to_thread(media_store.save, content, mime_type)
        try:
            analysis = await asyncio.to_thread(
                analyzer.analyze_bytes,
                content,
                mime_type,
                upload.filename or stored.media_id,
            )
            embedding = analysis.pop("embedding", [])
            analysis["embedding_dimensions"] = len(embedding)
            analysis_status = (
                "analyzed" if analysis["pipeline"]["execution"] == "live" else "queued"
            )
        except Exception as exc:  # The other photos in a batch should still be retained.
            failures += 1
            embedding = []
            analysis = {
                "usefulness": "UNKNOWN",
                "scene_type": "analysis_error",
                "candidate_subject": "Unsorted",
                "description": "The photo was saved, but cloud analysis did not complete.",
                "entities": [],
                "quality": {"usable": True, "coverage_note": "Analysis unavailable."},
                "embedding_dimensions": 0,
                "pipeline": {
                    "execution": "error",
                    "reasoning_model": settings.gemini_model,
                    "error": type(exc).__name__,
                },
            }
            analysis_status = "analysis_failed"

        title = _photo_title(upload.filename or "Imported photo")
        event_id = None
        if event_publisher is not None:
            try:
                event_id = await asyncio.to_thread(
                    event_publisher.publish,
                    {
                        "event_type": "media.indexed",
                        "media_id": stored.media_id,
                        # The anonymous owner token (not PII) so the asynchronous stage
                        # consolidates each visitor's subject state in isolation.
                        "owner_id": owner,
                        "source": source,
                        "storage_key": stored.storage_key,
                        "captured_at": captured_at,
                        "usefulness": analysis.get("usefulness", "UNKNOWN"),
                        "models": analysis.get("pipeline", {}),
                    },
                )
            except Exception:
                event_failures += 1
        record: dict[str, object] = {
            "id": stored.media_id,
            "owner_id": owner,
            "image": stored.url,
            "captured_at": captured_at,
            "capture_time_source": capture_time_source,
            "title": title,
            "category": _gallery_category(str(analysis.get("usefulness", "UNKNOWN"))),
            "source": source,
            "origin": "Your connected photos",
            "imported": True,
            "status": analysis_status,
            "storage_key": stored.storage_key,
            "storage_backend": stored.backend,
            "mime_type": mime_type,
            "sha256": digest,
            "_embedding": embedding,
            "pipeline_event_id": event_id,
            "analysis": analysis,
        }
        items.append(await asyncio.to_thread(repository.add_upload, record))

    run = {
        "id": f"ing_{uuid4().hex[:10]}",
        "source": source,
        "status": "completed" if failures + event_failures == 0 else "completed_with_errors",
        "started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "discovered": len(files),
        "deduplicated": len(duplicates),
        "indexed": len(items),
        "physical_state_useful": sum(
            item["analysis"].get("usefulness", "").startswith("PHYSICAL_STATE")  # type: ignore[union-attr]
            for item in items
        ),
        "subjects_updated": len(
            {
                item["analysis"].get("candidate_subject")  # type: ignore[union-attr]
                for item in items
                if item["analysis"].get("candidate_subject") != "Unsorted"  # type: ignore[union-attr]
            }
        ),
        "events_proposed": 0,
        "transport": "vertex_ai_pubsub" if settings.live_model_enabled else "local_pending",
        "failures": failures,
        "event_failures": event_failures,
    }
    await asyncio.to_thread(repository.add_ingestion_run, run)
    return {"items": items, "duplicates": duplicates, "run": run}


@app.get("/api/v1/media/{media_id}")
def media(media_id: str, owner: str = Depends(resolve_owner)) -> Response:
    # Ownership is checked before a byte is read: a media id from another visitor's
    # gallery resolves to nothing here.
    item = repository.upload(media_id, owner)
    if item is None:
        raise HTTPException(status_code=404, detail="media not found")
    try:
        content = media_store.read(str(item["storage_key"]))
    except (FileNotFoundError, OSError):
        raise HTTPException(status_code=404, detail="media content not found") from None
    mime_type = str(item.get("mime_type", "image/jpeg"))
    return Response(
        content=content,
        media_type=mime_type,
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )


@app.delete("/api/v1/media/{media_id}", status_code=204)
async def delete_media(media_id: str, owner: str = Depends(resolve_owner)) -> Response:
    item = repository.upload(media_id, owner)
    if item is None:
        raise HTTPException(status_code=404, detail="media not found")
    try:
        await asyncio.to_thread(media_store.delete, str(item["storage_key"]))
        deleted = await asyncio.to_thread(repository.delete_upload, media_id, owner)
    except Exception:  # Storage and Firestore expose provider-specific exception types.
        raise HTTPException(status_code=503, detail="media deletion did not complete") from None
    if not deleted:
        raise HTTPException(status_code=404, detail="media not found")
    return Response(status_code=204)


def _pipeline_authorized(request: Request) -> bool:
    token = settings.pipeline_token
    if not token:
        return False
    header = request.headers.get("authorization", "")
    provided = request.query_params.get("token") or (
        header[7:] if header.lower().startswith("bearer ") else ""
    )
    return bool(provided) and secrets.compare_digest(provided, token)


@app.post("/api/v1/pipeline/media-indexed", include_in_schema=False)
async def pipeline_media_indexed(request: Request) -> Response:
    """Pub/Sub push target for the asynchronous state-construction stage.

    This is not a user endpoint. Even though the demo service grants public invoke, the
    stage is gated by a shared pipeline token that only Pub/Sub's push subscription carries,
    so the open invoker permission cannot drive it. It returns 2xx to acknowledge a message
    and a 5xx only on an unexpected fault, letting the subscription's retry and dead-letter
    policy handle genuine failures.
    """
    if not settings.pipeline_token:
        raise HTTPException(status_code=503, detail="pipeline worker not configured")
    if not _pipeline_authorized(request):
        raise HTTPException(status_code=403, detail="forbidden")
    try:
        envelope = await request.json()
    except Exception:
        # A body Pub/Sub can never re-serialize into valid JSON: ack so it does not loop.
        return JSONResponse(status_code=200, content={"status": "ignored", "reason": "bad_body"})
    event = decode_pubsub_event(envelope)
    if event is None:
        return JSONResponse(status_code=200, content={"status": "ignored", "reason": "malformed"})
    result = await asyncio.to_thread(
        consolidator.consolidate, str(event["media_id"]), event.get("owner_id")
    )
    return JSONResponse(status_code=200, content=result)


@app.get("/api/v1/proof")
def proof() -> dict[str, object]:
    fixture = repository.bootstrap()
    return {
        "claim": "The demo is a deterministic fixture; production adapters are present but not impersonated.",
        "requirements": {
            "gemini": settings.gemini_model,
            "gallery_triage": settings.triage_model,
            "agent_framework": "Google ADK",
            "cloud": ["Cloud Run", "Firestore", "Cloud Storage", "Pub/Sub"],
            "multimodal_retrieval": settings.embedding_model,
        },
        "fixture": {
            "synthetic": True,
            "assets": len(fixture["assets"]),
            "subjects": len(fixture["subjects"]),
            "ground_truth_questions": 6,
        },
    }


app.mount("/assets", StaticFiles(directory=settings.web_root / "assets"), name="assets")
app.mount("/fixtures", StaticFiles(directory=settings.web_root / "fixtures"), name="fixtures")
# Uploaded media is never served from a public static mount. Every backend goes through the
# owner-checked /api/v1/media/{id} route, so isolation cannot be bypassed by URL.


@app.get("/", include_in_schema=False)
@app.get("/{path:path}", include_in_schema=False)
def web_app(path: str = "") -> FileResponse:
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API route not found")
    candidate = settings.web_root / path
    if path and candidate.is_file() and candidate.resolve().is_relative_to(settings.web_root.resolve()):
        return FileResponse(candidate)
    return FileResponse(settings.web_root / "index.html")


def _inspect_image(content: bytes) -> tuple[str, str, str] | None:
    try:
        with Image.open(BytesIO(content)) as image:
            if image.width * image.height > 40_000_000:
                return None
            image_format = image.format
            exif = image.getexif()
            captured_at, time_source = _capture_time(exif)
            image.verify()
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError):
        return None
    mime_type = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}.get(
        image_format
    )
    if mime_type is None:
        return None
    return mime_type, captured_at, time_source


def _capture_time(exif: object) -> tuple[str, str]:
    get = getattr(exif, "get", None)
    if callable(get):
        raw_time = get(36867) or get(306)  # DateTimeOriginal, then DateTime.
        raw_offset = get(36881) or ""  # OffsetTimeOriginal.
        if isinstance(raw_time, str):
            try:
                if isinstance(raw_offset, str) and raw_offset:
                    captured = datetime.strptime(raw_time + raw_offset, "%Y:%m:%d %H:%M:%S%z")
                    return captured.isoformat(), "exif"
                captured = datetime.strptime(raw_time, "%Y:%m:%d %H:%M:%S")
                return captured.isoformat(), "exif_local"
            except ValueError:
                pass
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "upload_time"


def _photo_title(filename: str) -> str:
    stem = filename.rsplit(".", 1)[0]
    cleaned = " ".join(stem.replace("_", " ").replace("-", " ").split())
    return cleaned[:80].title() or "Imported photo"


def _gallery_category(usefulness: str) -> str:
    return {
        "DOCUMENT": "Documents",
        "SCREENSHOT": "Screenshots",
        "PORTRAIT": "People & pets",
        "SCENERY": "Trips",
        "FOOD": "Food",
    }.get(usefulness, "Everyday")
