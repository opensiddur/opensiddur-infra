# Architecture

Firebase Hosting serves the React client and proxies `/api/**` and authenticated internal callbacks to Cloud Run. The API verifies Firebase tokens, resolves an internal account UUID, validates settings with the actual pinned processor, and stores transactional quota/build records in Firestore. All database access is server-side.

Full builds and previews use the same durable admission path. A build document is also an outbox: task creation may fail without losing accepted work. Cloud Tasks launches full Cloud Run jobs or calls the private preview service. Every worker transactionally claims the build and a concurrency slot before invoking the processor. Duplicate deliveries cannot compile twice. Worker subprocesses have their own working directory and SQLite reference database. Cancellation is polled while subprocesses run; process groups are killed when cancelled or out of time.

Print and electronic compilations are separate. HTML is built first so a later PDF error does not prevent successful HTML from being retained. Publication records artifacts after checking that the account/build remains active; the cancellation transaction prevents publication even if cancellation races with the final upload. Reconciliation removes unreferenced uploads.

## Public API

- `GET /api/v1/catalog`, `/schema`, `/notices`, `/health`
- `POST /api/v1/validate`
- Authenticated `GET /account`, `POST|DELETE /consent`, `GET /account/export`, `DELETE /account`
- Authenticated `GET|POST /builds`, `GET|DELETE /builds/{uuid}`, `POST /builds/{uuid}/cancel`
- `POST /builds/{uuid}/share` with `{enabled: true|false}`; enabling rotates the bearer UUID
- `GET /builds/{uuid}/files/{name}` or `?redirect=false` for a short-lived URL as JSON
- `GET /builds/{uuid}/preview` for an isolated, script-disabled HTML sample
- Public `GET /shares/{shareUuid}`, `/shares/{shareUuid}/files/{name}` for shared PDF/HTML only
- Authenticated `GET /presets`, `PUT|DELETE /presets/{uuid}`, `POST /assets` with PNG/JPEG bytes

Build request: `{release, settings, formats, type, idempotency_key, asset?}`. `type` is `full`, `html` (preview), or `pdf` (sample); formats are `pdf`, `html`, `tex`, `xml`. Returns 202 with the UUID and state. Settings follow the upstream model. Different payloads cannot reuse an idempotency key.

Status reports a stage and per-format results, not estimated percentages. 422 identifies invalid settings; 429 is an allowance limit; 409 indicates an outstanding operation or changed release. Build/preview requests additionally require App Check in production. All ownership checks are based on the internal account UUID.

Firestore records have deterministic hashed document names and an explicit kind. Transactions read all participating documents before writes. Quotas use admission-day ledgers; runtime and concurrency reservations are shared across API instances. No in-process counters enforce global limits.

Private object prefixes use random build UUIDs. Sharing has a different random UUID, stored only as a hash. Share metadata omits identity/settings and excludes ZIP/source/settings downloads. Owners and share holders get signed URLs valid for at most five minutes and no later than expiry. HTML books download as attachments. Samples run in sandboxed iframes without same-origin or script privileges.
