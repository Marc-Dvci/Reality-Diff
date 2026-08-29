# Architecture

The maintained diagram is [reality-diff-architecture.svg](architecture/reality-diff-architecture.svg).

## Request and evidence flow

1. Web or Android submits explicit user-selected JPEG, PNG, or WebP media.
2. The API validates every file before mutation, extracts EXIF capture time, and skips an existing SHA-256 hash.
3. Local mode writes an unprocessed gallery item to local storage with a visible queued state.
4. Cloud mode stores the original in private Cloud Storage, uses Gemini 3.5 Flash-Lite for usefulness triage, and uses Gemini 3.7 Flash for a visible-facts-only structured observation when appropriate.
5. Gemini Embedding 2 produces a 768-dimensional image vector stored only in server-side state.
6. The upload request publishes a `media.indexed` event and returns. A Pub/Sub push subscription then drives the asynchronous **state-construction stage** (`/api/v1/pipeline/media-indexed`), which groups the subject's observations, orders them by capture time, proposes the candidate transitions between consecutive observations, and commits that consolidation to Firestore. Because delivery is push, the stage runs only on an event and the service still scales to zero; retries and a dead-letter topic absorb genuine failures.
7. Unknown user questions are embedded as retrieval queries. The top private observations are passed to Gemini 3.7 Flash with their allowed IDs.
8. The API rejects generated evidence IDs that were not in the retrieved set and returns an `Answer` with source-image links and a coverage note.
9. Google ADK exposes the same deterministic temporal search, subject inspection, and explicit-memory operations as bounded tools.

## Per-visitor isolation

The public demo needs no account, so a visitor's imports must still be private to that visitor. On first contact the API sets a random, opaque owner token in an `HttpOnly`, `SameSite=Lax` cookie (`rd_owner`); every subsequent request carries it automatically to `fetch`, `<img>`, and `DELETE`.

- Every upload, gallery/bootstrap view, hash-dedup, media retrieval, deletion, correction, and reasoning path is scoped to that owner. A media id from one visitor's gallery resolves to a 404 for any other visitor, and originals are served only through the owner-checked `/api/v1/media/{id}` route, never a public static mount.
- The owner is always taken from the cookie, never from a request body, so a client cannot claim another owner. The token is stripped from every response payload.
- The Google ADK partner isolates on the same token: its session is keyed on the owner, and the evidence tools read the owner from session state so an orchestrated turn can only reach the visitor's own uploads and corrections.
- The token is not identity or PII; it distinguishes browsers, not people, and no account, email, or profile is ever collected.

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
- The state-construction stage acknowledges permanently unprocessable messages (malformed payload, or media that no longer exists) so they cannot loop, and returns a 5xx only on an unexpected fault so the subscription retries and finally dead-letters it. The stage reloads authoritative Firestore state before it reads, so a push that lands on a different Cloud Run instance than the upload still sees the photo and its siblings.
- The push endpoint is gated by a shared pipeline token held only by the Cloud Run container and the push subscription URL, so the public invoke permission cannot drive the internal stage; production also authenticates the push with an OIDC token at the Cloud Run layer.
- Unsupported or oversized content is rejected before any file in that request is stored.
- Missing evidence produces `uncertain`; ambiguous physical regions produce `clarification_required`.
- The immutable fixture keeps the app useful if external credentials or quota are unavailable.
