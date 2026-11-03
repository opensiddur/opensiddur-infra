# Deployment verification (2026-11-02)

The repository and local worktrees are created. The implementation is in [draft PR #1](https://github.com/opensiddur/opensiddur-infra/pull/1).

## Completed checks

- 25 backend tests using synthetic data, 24 frontend regression and interaction tests, TypeScript/Vite production build, dependency audit, Terraform formatting/validation, and GitHub CI.
- Local browser checks loaded 141 projects from the real development API. Existing presets, source reordering, typography editing and YAML round trips preserved font names, processor aliases and false/null custom declarations. The software-notice page loaded the deployed inventory.
- The real development stack generated PDF, HTML, TeX, print/electronic XML, settings, metadata, notices and ZIP through Cloud Tasks OIDC, the API, Cloud Run Jobs, Firestore and private Storage. Private HTML preview dispatch passed separately.
- API-service-account IAM signing and an actual signed-URL Storage download passed. Synthetic account records and artifacts were removed.

The earlier [Cloud Build smoke run](https://console.cloud.google.com/cloud-build/builds/ac2e73dc-440f-4e52-89fd-cd2ff2b0f2e1?project=817628492067) passed for release `edb5a9dd7f2a8184fe35` (implementation source `fb1279d`). That release was deployed in development. Post-deployment full-build and private PDF-preview probes passed, including actual artifact reads and removal of synthetic accounts/files. Public health/catalog requests returned 200; unauthenticated account, build and validation requests returned 401.

Container verification runs the actual unprivileged worker with a private writable SQLite database. It validates every bundled preset, tests canonical settings round trips, constructs both ASGI applications, and generates all output formats before permitting image promotion.

## Current launch boundary

Dedicated projects `opensiddur-builder-dev` and `opensiddur-builder-prod` have separate foundations, private remote state, GitHub deployment identities and budget alerts. Only development has runtime services. Public submissions remain disabled; production has no operator allowlist.

Firebase activation is complete for both projects after the operator accepted the account terms. Terraform manages each project's web app, email-link authentication, Hosting site and deny-all browser database rules. Development Hosting is published at https://opensiddur-builder-dev.web.app; the API rewrite, Firebase initialization and privacy page return 200. Its maintenance schedule is enabled. Production still has no runtime or published application release.

Local Terraform working data is now isolated by environment to prevent backend selection from crossing environments in one checkout. Development's activation plan contained no deletions. Both Firebase projects remain ACTIVE.

The operator reports that email-link delivery and sign-in work. Broader account/build acceptance testing remains. Google OAuth client configuration, production App Check registration, and finalized worldwide privacy/controller details remain launch prerequisites. Public submissions remain disabled. See [deployment instructions](deployment.md) and [privacy responsibilities](privacy.md).

Complete the remaining browser acceptance pass: explicit consent, automatic HTML and manual PDF samples, full build, private downloads, share rotation/revocation, saved preset/logo reuse, account export, consent withdrawal and deletion. Public anonymous browsing must still work without consent; protected endpoints must reject unauthenticated access and other owners' UUIDs.

## Builder usability review

The updated builder is deployed at https://opensiddur-builder-dev.web.app. Release `a8913424d69b3887173f`, implementation source `d0a8a3c`, passed the [real-worker Cloud Build smoke test](https://console.cloud.google.com/cloud-build/builds/5a098fc6-d03b-41d7-a68e-82363ee60ee4?project=817628492067). The update reuses the official logo and the website's orange/blue styling, removes invented taglines, displays source titles/languages, preserves published preset selection, adds source-priority help, places previews next to settings, and uses one remembered advanced-mode switch. Personal presets persist advanced/output preferences, and the account's remaining daily allowance replaces fixed quota descriptions.

Browser checks switched between Documentary and Expanded presets and confirmed different YAML, checked advanced-mode persistence and hiding, expanded help text, and verified preview placement at desktop width and at 615px without horizontal overflow. The logo's original attribution metadata is preserved and its separate CC BY-SA 4.0 notice is included publicly and in generated notices.

Post-deployment checks confirm the API reports the new release, the hosted logo is byte-identical to the preserved source asset, and generated notices include its CC BY-SA 4.0 attribution. The hosted preset selector, translation help and desktop typography/preview placement passed browser review without console errors.

## Search, account navigation and license follow-up

Implementation source `912d830` replaces the separate catalog/source search inputs and selects with one accessible searchable dropdown. It ranks matching titles, supports Arrow/Enter/Escape keyboard interaction, shows up to eight matches and excludes already-selected sources. Account controls are on a dedicated view reached from the upper-right Account menu, with sign-in and signed-in sign-out controls. Returning from the account view retains the chosen book and settings; email-link callbacks open that account view.

The licenses page uses a concise summary even when a package stores its full license in the metadata label, and preserves that full text inside the expandable notice. Synthetic DOM interaction tests cover filtering, keyboard selection, duplicate prevention, account navigation with retained settings and the license disclosure. All 25 backend and 14 frontend checks pass. Browser automation was unavailable for this follow-up, so no new visual browser acceptance pass is claimed.

The follow-up is deployed as release `414815b1fb8bd05a0fc8`. Its [Cloud Build smoke test](https://console.cloud.google.com/cloud-build/builds/ac60f20e-17be-4589-9054-47fd4ce7bebd?project=817628492067) passed. Post-deployment HTTP checks confirm the API release and that `/`, `/account`, `/login` and `/licenses` serve the tested bundle; the hosted JavaScript is byte-identical to the production build. Live Hyperframe metadata matches the full-text case covered by the disclosure tests. The browser access host remained unavailable for a visual recheck.

## Typed controls and inherited defaults

The settings editor now renders enum/boolean choices and bounded numeric ranges as selectors with a `(default)` option. Free text and unrestricted numbers are editable fields with a default reset. Continuous numeric ranges retain a custom-number entry so permitted fractional values remain available. Object groups expand without creating an override. References preserve property-level defaults, including parallel layout's `pairs` default, rather than inserting an empty enum value.

Customs numeric and symbol settings use the same direct controls, removing the intermediate Set-value step that could insert invalid zero/empty-string values. New list entries and incomplete structured values remain drafts; preview, save and build wait until those edits are completed or cancelled. Font and running-header shorthand is normalized to editable schema objects without changing its meaning.

Synthetic tests cover direct `pages` selection, group expansion without mutations, default removal, explicit false/null, bounded and continuous numeric choices, staged required values, staged font-list entries, Customs choices and the complete builder-to-YAML path. All 25 backend and 24 frontend tests pass. A one-off compatibility check accepted all six normalized published presets. Browser automation remained unavailable.

Text-editing regressions additionally distinguish a valid explicit empty string from resetting an override to default, and verify that clearing/replacing a required font name retains the entry and its size. The final frontend correction changes only `web/src` relative to source `5ead148`; it is layered over the previously verified compiler image for release `1e213ff3514ad87100ce`, regenerates bundle metadata/notices, and reruns the unprivileged worker export smoke test. The normal full-source deployment scripts remain applicable.

The final typed-controls update is deployed as release `aa6ccdd722304371237b`, source `0e07d5d`. Its [image smoke test](https://console.cloud.google.com/cloud-build/builds/0c3d5117-9593-467c-8fe7-9265a94c7274?project=817628492067) passed all compiler output formats. Post-deployment checks confirmed the API release and that Hosting serves the byte-identical tested production JavaScript. All 25 backend and 24 frontend checks pass; live visual browser verification remains unavailable.


## Print layout preview

The HTML renderer applies selected fonts, paragraph styles and markers but ignores print parallel-layout settings. The builder now switches to the actual PDF renderer when Typography opens, with an explicit selector for reflowing HTML versus print layout. The fixed Psalm 23 sample still needs matching translation coverage for parallel columns. Existing ten-per-day PDF sample and preview runtime limits remain enforced; the UI displays the remaining PDF count.

All 26 backend and 25 frontend tests pass, including a complete App interaction that changes Pages to Pairs and verifies two distinct PDF requests and replacement of the displayed document. The previous object URL is revoked. API tests verify owner-only access, PDF content type, no-store caching and the remaining allowance. TypeScript/Vite production build and all GitHub checks pass. The new sample can be downloaded if the browser cannot embed PDF. The browser access host was unavailable, so no live visual acceptance pass is claimed.

Deployed source `d0e91ae` as development release `5e439c65cea919731676`. The [full image build](https://console.cloud.google.com/cloud-build/builds/9801c1ad-44d9-4d9e-8784-c5fc304d4fa8?project=817628492067) passed its actual unprivileged compiler test across all formats. Post-deployment health reports this release, Hosting serves byte-identical tested JavaScript, and unauthenticated preview access returns 401. A synthetic live PDF preview traversed Cloud Tasks → API OIDC → preview worker → Firestore → Storage successfully; its account and artifacts were removed.


## Preset forms and build views

Preset save/rename now uses inline name fields with Save/Cancel, blank-name validation, pending state and retained input after errors. A synthetic full-App interaction disables native `prompt()` and verifies saved settings/output preferences and renaming still work. Output choices and Build follow settings; an accepted full build opens `/builds/{uuid}` and polls until terminal status. Tests cover submission, running-stage updates, completion/download controls and retaining the selected settings when returning to Builder.

Build history is a separate navigation view containing only full books. Every row shows its status; active rows include their stage, while final rows omit results/downloads and link to the detailed status page. Sample builds are absent. Daily text/PDF counts come from the quota ledger and are shown against each limit. Tests verify compact final rows, active status, sample filtering and quota counts. All 26 backend and 28 frontend tests, TypeScript/Vite build and required GitHub checks pass. Browser automation remained unavailable, so no new visual browser acceptance is claimed.

Deployed implementation `b8c2314` as development release `b987eed3ac7307fa2464`. The [Cloud Build compiler smoke test](https://console.cloud.google.com/cloud-build/builds/d80b5590-fe50-4d76-a031-388b272f1c8f?project=817628492067) passed. This update layers the changed UI and account quota response over the verified immutable compiler image for release `5e439c65cea919731676`, regenerates metadata/notices and reruns actual worker export checks. The normal full-source deployment remains supported. Live health reports the new release; `/`, `/builds` and an individual build URL serve byte-identical tested JavaScript. Unauthenticated build-status API access returns 401.
