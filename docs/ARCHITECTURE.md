# Architecture

The maintained diagram is [reality-diff-architecture.svg](architecture/reality-diff-architecture.svg).

## Request and evidence flow

1. Web or Android submits explicit user-selected JPEG, PNG, or WebP media.
2. The API validates every file before mutation, extracts EXIF capture time, and skips an existing SHA-256 hash.
3. Local mode writes an unprocessed gallery item to local storage with a visible queued state.
4. Cloud mode stores the original in private Cloud Storage, uses Gemini 3.5 Flash-Lite for usefulness triage, and uses Gemini 3.7 Flash for a visible-facts-only structured observation when appropriate.
5. Gemini Embedding 2 produces a 768-dimensional image vector stored only in server-side state.
6. Unknown user questions are embedded as retrieval queries. The top private observations are passed to Gemini 3.7 Flash with their allowed IDs.
7. The API rejects generated evidence IDs that were not in the retrieved set and returns an `Answer` with source-image links and a coverage note.
8. Google ADK exposes the same deterministic temporal search, subject inspection, and explicit-memory operations as bounded tools.

## Persistence

| Concern | Local/sample | Google Cloud |
|---|---|---|
| Originals | `var/uploads` | Private Cloud Storage bucket |
| Mutable state | Atomic `var/demo-state.json` | Firestore collections |
| Pipeline metadata | Local ingestion record | Firestore plus Pub/Sub event |
| Immutable sample | `web/fixtures/demo.json` | Bundled in the container |

Uploads, corrections, and ingestion runs are protected with an in-process lock locally. Firestore supplies cross-instance durability on Cloud Run. The server never includes storage object keys, hashes, or embedding vectors in gallery/bootstrap payloads.

## Failure behavior

- One Gemini failure retains the original, marks that item `analysis_failed`, and lets the rest of the valid batch continue.
- A Pub/Sub publishing failure is reported in the ingestion run rather than changing a successful model result into a false success.
- Unsupported or oversized content is rejected before any file in that request is stored.
- Missing evidence produces `uncertain`; ambiguous physical regions produce `clarification_required`.
- The immutable fixture keeps the app useful if external credentials or quota are unavailable.
