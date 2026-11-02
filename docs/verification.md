# Deployment verification (2026-11-02)

The repository and local worktrees are created. The implementation is in [draft PR #1](https://github.com/opensiddur/opensiddur-infra/pull/1).

## Completed checks

- 25 backend tests using synthetic data, seven frontend regression tests, TypeScript/Vite production build, dependency audit, Terraform formatting/validation, and GitHub CI.
- Local browser checks loaded 141 projects from the real development API. Existing presets, source reordering, typography editing and YAML round trips preserved font names, processor aliases and false/null custom declarations. The software-notice page loaded the deployed inventory.
- The real development stack generated PDF, HTML, TeX, print/electronic XML, settings, metadata, notices and ZIP through Cloud Tasks OIDC, the API, Cloud Run Jobs, Firestore and private Storage. Private HTML preview dispatch passed separately.
- API-service-account IAM signing and an actual signed-URL Storage download passed. Synthetic account records and artifacts were removed.

The earlier [Cloud Build smoke run](https://console.cloud.google.com/cloud-build/builds/ac2e73dc-440f-4e52-89fd-cd2ff2b0f2e1?project=817628492067) passed for release `edb5a9dd7f2a8184fe35` (implementation source `fb1279d`). That release was deployed in development. Post-deployment full-build and private PDF-preview probes passed, including actual artifact reads and removal of synthetic accounts/files. Public health/catalog requests returned 200; unauthenticated account, build and validation requests returned 401.

Container verification runs the actual unprivileged worker with a private writable SQLite database. It validates every bundled preset, tests canonical settings round trips, constructs both ASGI applications, and generates all output formats before permitting image promotion.

## Current launch boundary

Dedicated projects `opensiddur-builder-dev` and `opensiddur-builder-prod` have separate foundations, private remote state, GitHub deployment identities and budget alerts. Only development has runtime services. Public submissions remain disabled; production has no operator allowlist.

Firebase activation is complete for both projects after the operator accepted the account terms. Terraform manages each project's web app, email-link authentication, Hosting site and deny-all browser database rules. Development Hosting is published at https://opensiddur-builder-dev.web.app; the API rewrite, Firebase initialization and privacy page return 200. Its maintenance schedule is enabled. Production still has no runtime or published application release.

Local Terraform working data is now isolated by environment to prevent backend selection from crossing environments in one checkout. Development's activation plan contained no deletions. Both Firebase projects remain ACTIVE.

Browser sign-in/account acceptance testing still requires the operator to follow the email link. Google OAuth client configuration, production App Check registration, and finalized worldwide privacy/controller details remain launch prerequisites. Public submissions remain disabled. See [deployment instructions](deployment.md) and [privacy responsibilities](privacy.md).

Complete the browser acceptance pass after activation: email-link sign-in, explicit consent, automatic HTML and manual PDF samples, full build, private downloads, share rotation/revocation, saved preset/logo reuse, account export, consent withdrawal and deletion. Public anonymous browsing must still work without consent; protected endpoints must reject unauthenticated access and other owners' UUIDs.

## Builder usability review

The updated builder is deployed at https://opensiddur-builder-dev.web.app. Release `a8913424d69b3887173f`, implementation source `d0a8a3c`, passed the [real-worker Cloud Build smoke test](https://console.cloud.google.com/cloud-build/builds/5a098fc6-d03b-41d7-a68e-82363ee60ee4?project=817628492067). The update reuses the official logo and the website's orange/blue styling, removes invented taglines, displays source titles/languages, preserves published preset selection, adds source-priority help, places previews next to settings, and uses one remembered advanced-mode switch. Personal presets persist advanced/output preferences, and the account's remaining daily allowance replaces fixed quota descriptions.

Browser checks switched between Documentary and Expanded presets and confirmed different YAML, checked advanced-mode persistence and hiding, expanded help text, and verified preview placement at desktop width and at 615px without horizontal overflow. The logo's original attribution metadata is preserved and its separate CC BY-SA 4.0 notice is included publicly and in generated notices.

Post-deployment checks confirm the API reports the new release, the hosted logo is byte-identical to the preserved source asset, and generated notices include its CC BY-SA 4.0 attribution. The hosted preset selector, translation help and desktop typography/preview placement passed browser review without console errors.
