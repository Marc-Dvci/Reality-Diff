# Reality Diff

**Semantic memory for the physical world.** Reality Diff turns an ordinary photo history into an evidence-linked model of persistent places, objects, vehicles, and projects. It answers what changed, when the evidence bounds that change, and what the original photographs actually prove.

The project is a complete responsive web product, FastAPI service, Google ADK agent, and native Android client. It has a zero-credential sample mode and a live Google Cloud mode; the UI always labels which one is active.

## Product capabilities

- Google Photos-style gallery with 18 licensed lifestyle photos and eight synthetic evidence photos, date grouping, filters, search, responsive lightbox, and model provenance.
- Real browser folder selection, multi-file selection, and drag-and-drop. The UI accepts up to 60 photos and sends safe 12-photo batches.
- JPEG, PNG, and WebP content verification, 12 MB and 40-megapixel limits, SHA-256 deduplication, EXIF capture-time extraction, private storage, and deletion.
- `gemini-3.5-flash-lite` first-pass visual triage.
- `gemini-3.7-flash` schema-constrained visible-state analysis and grounded temporal answers.
- `gemini-embedding-2` 768-dimensional image/question retrieval. Vectors stay server-side and returned evidence IDs are validated before display.
- Google ADK collaborative partner with bounded temporal search, subject inspection, and explicit correction-memory tools.
- Evidence-linked sample questions with ambiguity handling, last-seen/first-seen intervals, coverage-aware uncertainty, and persistent corrections.
- Native Android Photo Picker, optional MediaStore discovery, incremental JobScheduler sync, safe multipart upload, and shared sample assets—without a WebView.
- Cloud Run, Firestore, Cloud Storage, Pub/Sub, Artifact Registry, least-privilege service identity, health probes, and dead-letter infrastructure in Terraform.

## Google model stack

| Stage | Model/service | Purpose |
|---|---|---|
| Triage | `gemini-3.5-flash-lite` | Reject low-value gallery noise cheaply |
| Understand and reason | `gemini-3.7-flash` | Multimodal observations and evidence-safe answers |
| Retrieve | `gemini-embedding-2` | Shared image/text retrieval space |
| Orchestrate | Google ADK 2.x | Tool-bounded collaborative partner |
| Persist and serve | Cloud Run, Firestore, Cloud Storage, Pub/Sub | Scalable Google Cloud runtime |

Gemini 3.7 Flash runs at the supported `global` Vertex AI location. Cloud Run and data resources default to `us-central1`; those locations are intentionally configured separately.

## Run locally

Python 3.10+ is supported; Python 3.12 is used by the container.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
uvicorn realitydiff.api:app --reload --port 8091
```

Open <http://127.0.0.1:8091>. API documentation is at <http://127.0.0.1:8091/docs>.

Without cloud credentials, uploads are genuinely stored under `var/uploads`, appear in the gallery, and are clearly marked `queued`; the app does not pretend that Gemini ran. To exercise the official Google imports locally:

```powershell
python -m pip install -e ".[google]"
```

For live Vertex AI execution:

```powershell
gcloud auth application-default login
$env:REALITYDIFF_ENV = "production"
$env:GOOGLE_CLOUD_PROJECT = "reality-diff"
$env:GOOGLE_CLOUD_LOCATION = "global"
$env:REALITYDIFF_GEMINI_MODEL = "gemini-3.7-flash"
$env:REALITYDIFF_TRIAGE_MODEL = "gemini-3.5-flash-lite"
$env:REALITYDIFF_EMBEDDING_MODEL = "gemini-embedding-2"
uvicorn realitydiff.api:app --port 8091
```

For a local Developer API experiment, set `GEMINI_API_KEY` instead of Vertex credentials. Never put that key in the frontend or Android APK.

## Build Android

Use JDK 17 and Android SDK 37:

```powershell
$env:REALITYDIFF_API_BASE_URL = "https://YOUR-HTTPS-SERVICE-URL"
Set-Location android
.\gradlew.bat :app:assembleDebug :app:lintDebug --no-daemon
```

The URL is compiled into `BuildConfig`; leave it empty for the offline sample. The APK is written to `android/app/build/outputs/apk/debug/app-debug.apk`. The app supports Android 10+ (API 29) and only performs full-library discovery after explicit permission.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check src tests
node --check web/app.js
python -m json.tool web/fixtures/demo.json > $null
python scripts/demo-smoke.py http://127.0.0.1:8091
node scripts/visual-smoke.mjs http://127.0.0.1:8091

Set-Location android
.\gradlew.bat :app:assembleDebug :app:lintDebug --no-daemon

Set-Location ..
docker build -t reality-diff:audit .
```

The detailed verification record is in [docs/BUILD_AUDIT.md](docs/BUILD_AUDIT.md).

## Google Cloud deployment

The private production deployment is live:

- Project ID: `reality-diff`
- Project number: `284853036406`
- Region: `us-central1` (`global` for Vertex AI)
- Cloud Run service: `reality-diff`
- Cost profile: scale to zero, at most two 1 vCPU / 512 MiB instances
- Budget alerts: project-scoped €10 monthly guardrail

The service is intentionally private until judge access is prepared. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for access and operations, and [docs/CLOUD_DEPLOYMENT_EVIDENCE.md](docs/CLOUD_DEPLOYMENT_EVIDENCE.md) for the live test record and screenshots.

## Repository map

```text
android/                 Native Android application and Gradle wrapper
docs/                    Architecture, asset provenance, deployment, audit
infrastructure/          Validated Google Cloud Terraform
src/realitydiff/         API, storage, retrieval, Gemini, ADK, persistence
tests/                   Deterministic unit and API tests
web/                     Responsive product and canonical fixture
```

## Privacy and evidence boundary

- Originals are local in sample mode and stored in a bucket with public-access prevention in Cloud mode.
- Hashes and embedding vectors never appear in bootstrap or upload responses.
- Imported media can be removed from the gallery, persistent state, and object storage.
- Gemini prompts prohibit identity and sensitive-trait inference.
- An observation timestamp bounds a change; it is not silently rewritten into an exact event time.
- Missing camera coverage produces uncertainty rather than a fabricated negative.
- The 18 Pexels photos are realistic gallery context, not evidence about a real person. Their exact sources are in [docs/ASSET_CREDITS.md](docs/ASSET_CREDITS.md).
- The eight evidence images and their metadata are synthetic and visibly disclosed in the product and `/api/v1/proof`.

Licensed under Apache-2.0. See [LICENSE](LICENSE), [NOTICE.md](NOTICE.md), and [REUSE_DISCLOSURE.md](REUSE_DISCLOSURE.md).
