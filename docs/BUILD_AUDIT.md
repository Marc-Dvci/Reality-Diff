# Build and contest audit

Audit date: 20 August 2026

## Product integrity

| Requirement | Evidence | Result |
|---|---|---|
| Real photo ingestion | Folder picker, file picker, drag/drop, Android picker and MediaStore multipart client | Pass |
| Upload safety | True-byte JPEG/PNG/WebP validation, 12 MB, 40 MP, batches of 12 | Pass |
| Efficient indexing | SHA-256 deduplication, Flash-Lite triage, 768-dimension multimodal embeddings | Pass |
| Capture chronology | EXIF time/offset when present; honest upload-time fallback | Pass |
| Live temporal retrieval | Image and question vectors ranked before Gemini 3.7 Flash reasoning | Pass |
| Grounded generation | Structured output plus server-side allow-list validation of evidence IDs | Pass |
| Multiple physical subjects | Home office, rental car, bike restoration | Pass |
| Temporal reasoning | Interval answer, continuity answer, project stages | Pass |
| Ambiguity handling | Generic scratch question requests a region | Pass |
| Missing-evidence refusal | Rear-right pickup coverage gap | Pass |
| Correction memory | Atomic local JSON or Firestore plus ADK correction tool | Pass |
| Media removal | Browser delete removes object and state; API returns 404 afterward | Pass |
| Honest runtime boundary | Runtime badge, queued local imports, and `/api/v1/proof` | Pass |
| Native Android | Photo Picker, MediaStore cursor, supported-type filter, JobScheduler, API upload | Pass |
| Google-style frontend | Material-like color, shape, density, typography, navigation, Photos-style gallery | Pass |
| Licensed realistic gallery | 18 bundled Pexels images across at least eight categories | Pass |

## Verification record

| Check | Result |
|---|---|
| Python unit/API/configuration/fixture tests | 23 passed, zero warnings |
| Ruff static analysis | Pass |
| Google SDK import and schema construction | ADK 2.7.1 / Gen AI 2.19.0 pass |
| ADK agent and App creation | `LlmAgent`, `App`, `gemini-3.7-flash` pass |
| Web JavaScript syntax | Pass |
| Fixture JSON parse and every gallery asset path | Pass |
| FastAPI health/readiness/bootstrap/proof/ask smoke | Pass |
| Docker non-root image build and container endpoint smoke | Pass |
| Terraform 1.15.8 formatting and Google provider v7.45 schema validation | Pass |
| Android debug compile | Pass |
| Android lint | Pass |
| Desktop visual smoke at 1440 px | Pass; all 26 gallery images load |
| Mobile visual smoke at 390 px | Pass; no horizontal overflow |
| Private Cloud Run deployment | Ready; final revision serves 100% of traffic |
| Production health and model configuration | Pass; live Vertex AI and all three exact model IDs |
| Live image ingestion | Pass; Storage, Firestore, Pub/Sub and three-model pipeline, zero failures |
| Live question-to-image retrieval | Pass; one grounded answer with a validated evidence ID |
| Production error-log check | Pass; no Cloud Run errors after end-to-end verification |
| Cloud deployment screenshots | Pass; desktop and mobile evidence set captured through authenticated proxy |

## Defects found and closed during the audit

- Upload controls previously simulated counts; they now upload and persist real media.
- The Gemini adapter was disconnected and used an older default; it now runs the exact three-model pipeline.
- Embeddings were computed but discarded; vectors now power question-to-image retrieval and remain private.
- Upload batches could partially mutate before a later invalid file; every file is now validated before storage begins.
- Duplicate photos were stored repeatedly; SHA-256 deduplication now reports and skips them.
- Browser and Android imported photos had no deletion path; storage and persistent-state deletion now exist.
- Android HEIC media could poison a retry batch and same-second timestamps could skip images; supported MIME filtering and a `(time, media-id)` cursor close both cases.
- The container could not create `/app/var/uploads` as its non-root user; writable state now lives under `/tmp` in container sample mode.
- TestClient used the deprecated HTTPX compatibility path; the suite now uses maintained HTTPX2.
- Terraform lacked an image registry and could target the wrong active gcloud project; Artifact Registry and a project-number assertion were added.

## Architecture decisions

- `gemini-3.5-flash-lite` handles low-cost filtering; only potentially useful physical/document observations reach `gemini-3.7-flash` reasoning.
- `gemini-embedding-2` replaces text-only retrieval and places images/questions in one 768-dimensional space.
- Known sample answers remain deterministic so evidence behavior can be evaluated without quota; unfamiliar questions use live retrieval only when Vertex AI is actually enabled.
- Public API responses omit object keys, SHA-256 hashes, and embedding vectors.
- Firestore stores mutable uploads, runs, and corrections; the canonical synthetic fixture remains immutable.
- Cloud Storage enforces public-access prevention; media is served through the application only after a known media record is resolved.
- Terraform defaults to a private Cloud Run service. Public access must be an explicit deployment choice.

## Explicit boundaries

- The repository is a single-user hackathon product, not a multi-tenant consumer service. A public production launch needs user authentication, per-user authorization, abuse controls, retention policy, and privacy-policy review.
- A browser cannot retain permanent folder access across every browser/platform; it requests access again when required by the File System Access API.
- Background Android sync requires full-library permission. The Photo Picker path remains available without that permission.
- The fixture reconstructs five bike stages from metadata, while two representative stage images are bundled.
- The debug APK uses the Android debug key. Store distribution requires an owner-controlled release keystore.
- The private Google Cloud deployment was applied on 20 August 2026 after explicit cost authorization. It scales to zero, is capped at two instances, and has a project-scoped €10 monthly alert budget. See `CLOUD_DEPLOYMENT_EVIDENCE.md`.
