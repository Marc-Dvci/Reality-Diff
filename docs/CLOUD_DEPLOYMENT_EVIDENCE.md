# Cloud deployment evidence

Verified on 20 August 2026 against Google Cloud project `reality-diff` (`284853036406`), when the service was still private; these captures used Google's authenticated Cloud Run proxy. The service was made public for judging on 27 August 2026 (`allUsers` → `roles/run.invoker`), and each visitor's uploads are isolated behind an anonymous per-browser token (see [ARCHITECTURE.md](ARCHITECTURE.md)).

## Deployed revision

| Item | Verified value |
|---|---|
| Cloud Run service | `reality-diff`, `us-central1` |
| Service URL | `https://reality-diff-284853036406.us-central1.run.app` |
| Ready revision | `reality-diff-v010-20260820-probes` |
| Traffic | 100% to the ready revision |
| Container image | `v0.1.0-20260820` in the immutable `reality-diff` repository |
| Image index digest | `sha256:1f35c1211b79699866954c676cc67cf871137b1c4607aedce181bab452db1a7e` |
| Runtime | 1 vCPU, 512 MiB, concurrency 8, 300-second timeout |
| Scaling | min 0, max 2; CPU throttled outside request handling |
| Health checks | HTTP `/ready` startup probe and `/health` liveness probe |
| Identity | `reality-diff-runtime@reality-diff.iam.gserviceaccount.com` |
| Access | Private at capture time; made public for judging on 27 August 2026 |

## Google services

- Vertex AI runs `gemini-3.5-flash-lite` for low-cost triage, `gemini-3.7-flash` for observation/reasoning, and `gemini-embedding-2` for 768-dimensional image/text retrieval. Model location is `global`.
- Firestore Native is the protected default database in `us-central1`; the API reports free-tier status and delete protection enabled.
- Cloud Storage bucket `reality-diff-reality-diff-media` enforces public-access prevention and uniform bucket-level access. It aborts incomplete multipart uploads after 30 days.
- Pub/Sub topic `reality-diff-ingestion` and its dead-letter topic are active. The worker subscription retains unacknowledged messages for one day and expires after prolonged inactivity.
- Artifact Registry enforces immutable tags. The deployed repository currently occupies approximately 124 MB; automatic container scanning was deliberately not enabled to avoid adding an unnecessary paid service for this hackathon deployment.

## Live end-to-end verification

The authenticated production health response reported:

```json
{
  "status": "ok",
  "mode": "production",
  "model": "gemini-3.7-flash",
  "triage_model": "gemini-3.5-flash-lite",
  "embedding_model": "gemini-embedding-2",
  "live_models": true,
  "google_cloud_project": "reality-diff",
  "google_cloud_location": "global"
}
```

A licensed gallery photo was then submitted to `/api/v1/media/analyze`:

- media ID `upload_7d640111192543f5`
- ingestion run `ing_d1d8be6fbb`
- status `analyzed`, Storage backend `gcs`
- triage result `PHYSICAL_STATE_HIGH_VALUE`
- live pipeline event `21491497033251590`
- 768 embedding dimensions
- zero ingestion failures and zero event-publication failures

The question “What durable objects and layout are visible in my recently imported living room photo?” then exercised question embedding, private observation retrieval, Gemini 3.7 Flash reasoning, and evidence-ID validation. It returned `answered`, high confidence, and exactly the imported media ID as evidence. A post-test Cloud Logging query found no Cloud Run errors.

The production deletion path was checked with a second temporary licensed image: upload and live triage completed with zero failures, `DELETE /api/v1/media/upload_669be2ed0717404a` returned HTTP 204, and the subsequent media request returned HTTP 404. The temporary Firestore document and GCS object were therefore removed.

## Screenshots

- [Live Vertex AI pipeline](evidence/desktop-sources.png): all three models, Google ADK, connected sources, and the completed production ingestion run.
- [Live Gemini photo analysis](evidence/desktop-live-photo.png): the uploaded GCS-backed image, Gemini 3.7 Flash provenance, and 768-dimensional Gemini Embedding 2 vector.
- [Desktop product](evidence/desktop-home.png) and [desktop gallery](evidence/desktop-gallery.png).
- [Mobile product](evidence/mobile-home.png), [mobile gallery](evidence/mobile-gallery.png), and [mobile agent](evidence/mobile-ask.png).

Every captured page passed the screenshot harness: no horizontal overflow and no failed image loads across the 27-photo live gallery.

## Cost controls

- Cloud Run scales to zero and cannot exceed two instances.
- No always-on worker, VM, database server, or GPU exists.
- The cheapest model handles triage; Gemini 3.7 Flash runs only on useful physical-state images and grounded questions.
- Firestore uses its free-tier database, Pub/Sub retention is one day, and Artifact Registry stores one immutable image tag.
- Billing budget `Reality Diff low-cost guardrail` is scoped only to project `284853036406`: €10 per month with actual-spend alerts at 50%, 80%, and 100%, plus a forecasted-spend alert at 100%. A budget alerts but does not automatically stop services.

## Private access

```powershell
gcloud run services proxy reality-diff --project reality-diff --region us-central1 --port 8091
```

Open `http://127.0.0.1:8091`. The service is now public for judging; this proxy remains available for private, authenticated access during development.
