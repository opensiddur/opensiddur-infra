# Architecture

Firebase Hosting serves the React client and proxies `/api/**` and authenticated internal callbacks to Cloud Run. The API verifies Firebase tokens, resolves an internal account UUID, validates settings with the actual pinned processor, and stores transactional quota/build records in Firestore. All database access is server-side.

Full builds and previews use the same durable admission path. A build document is also an outbox: task creation may fail without losing accepted work. Cloud Tasks launches full Cloud Run jobs or calls the private preview service. Every worker transactionally claims the build and a concurrency slot before invoking the processor. Duplicate deliveries cannot compile twice. Worker subprocesses have their own working directory and SQLite reference database. Cancellation is polled while subprocesses run; process groups are killed when cancelled or out of time.

Print and electronic compilations are separate. HTML is built first so a later PDF error does not prevent successful HTML from being retained. Publication records artifacts after checking that the account/build remains active; the cancellation transaction prevents publication even if cancellation races with the final upload. Reconciliation removes unreferenced uploads.

## Public API

- `GET /api/v1/catalog`, `/schema`, `/notices`, `/health`
- Authenticated, consent-gated `POST /api/v1/validate`
- Authenticated `GET /account`, `POST|DELETE /consent`, `GET /account/export`, `DELETE /account`
- Authenticated `GET|POST /builds`, `GET|DELETE /builds/{uuid}`, `POST /builds/{uuid}/cancel`
- `POST /builds/{uuid}/share` with `{enabled: true|false}`; enabling rotates the bearer UUID
- `GET /builds/{uuid}/files/{name}` or `?redirect=false` for a short-lived URL as JSON
- `GET /builds/{uuid}/preview` for an owner-only sample: isolated, script-disabled HTML or PDF bytes (no-store)
- Public `GET /shares/{shareUuid}`, `/shares/{shareUuid}/files/{name}` for shared PDF/HTML only
- Authenticated `GET /presets`, `PUT|DELETE /presets/{uuid}`, `POST /assets` with PNG/JPEG bytes

Build request: `{release, settings, formats, type, idempotency_key, asset?}`. `type` is `full`, `html` (preview), or `pdf` (sample); formats are `pdf`, `html`, `tex`, `xml`. Returns 202 with the UUID and state. Settings follow the upstream model. Different payloads cannot reuse an idempotency key.

Status reports a stage and per-format results, not estimated percentages. 422 identifies invalid settings; 429 is an allowance limit; 409 indicates an outstanding operation or changed release. Build/preview requests additionally require App Check in production. All ownership checks are based on the internal account UUID.

Firestore records have deterministic hashed document names and an explicit kind. Transactions read all participating documents before writes. Quotas use admission-day ledgers; runtime and concurrency reservations are shared across API instances. No in-process counters enforce global limits.

Private object prefixes use random build UUIDs. Sharing has a different random UUID, stored only as a hash. Share metadata omits identity/settings and excludes ZIP/source/settings downloads. Owners and share holders get signed URLs valid for at most five minutes and no later than expiry. HTML books download as attachments. Samples run in sandboxed iframes without same-origin or script privileges.

The builder switches to PDF preview when Typography opens, so parallel layout, page geometry and other print settings are rendered by the actual PDF exporter. PDF samples update after a 1.5-second pause; users can switch back to faster reflowing HTML, which does not implement print pagination or parallel layout. PDF previews use the existing ten-samples-per-day allowance and shared preview runtime budget. Old preview content is cleared on settings changes, stale responses are discarded, and PDF object URLs are revoked on replacement/sign-out. The fixed Psalm 23 sample needs matching translation coverage to demonstrate parallel columns.

The builder provides inline preset naming/renaming forms, without native browser prompts. Output choices and Build follow the settings; accepted builds open an owner-only `/builds/{uuid}` status page polling every two seconds until completion. The top-level Build history tab lists full books only, with current status and a stage for active builds. Finished history entries stay compact; detailed results, downloads, sharing and deletion are on each build page. Sample use is shown as daily HTML/PDF counts from the quota ledger, rather than individual history entries.

Loading personal presets and uploading settings YAML are available at the top of Settings without Advanced mode. Imports normalize supported shorthand and validate before replacing current choices; replacing settings resets incomplete editor drafts. Saved presets additionally restore their managed logo and display/output preferences. Save settings YAML is adjacent to Save preset. Build and manual print preview open account setup when sign-in/consent is missing; actual settings/output blockers remain disabled with explicit inline instructions.

Required selections and inputs carry an asterisk and accessible required/invalid attributes. Empty required choices are highlighted. The schema editor derives conditional requirements from the active object schema and excludes fields with inherited defaults; zero, false and permitted null values remain valid. Output selection requires at least one chosen format rather than marking every format checkbox required.

Saving a preset accepts a new name or an existing preset through a free-text combobox. Selecting an existing record, or typing its exact unique name, replaces that record via its existing UUID; the form states that its settings will be replaced. New names create new UUIDs. Renaming remains a separate operation.
