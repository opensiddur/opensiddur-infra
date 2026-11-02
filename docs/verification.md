# Deployment verification (2026-11-02)

The repository and local worktrees are created. The implementation is in [draft PR #1](https://github.com/opensiddur/opensiddur-infra/pull/1).

## Completed checks

- 24 backend tests using synthetic data, four frontend regression tests, TypeScript/Vite production build, dependency audit, Terraform formatting/validation, and GitHub CI.
- Local browser checks loaded 141 projects from the real development API. Existing presets, source reordering, typography editing and YAML round trips preserved font names, processor aliases and false/null custom declarations. The software-notice page loaded the deployed inventory.
- The real development stack generated PDF, HTML, TeX, print/electronic XML, settings, metadata, notices and ZIP through Cloud Tasks OIDC, the API, Cloud Run Jobs, Firestore and private Storage. Private HTML preview dispatch passed separately.
- API-service-account IAM signing and an actual signed-URL Storage download passed. Synthetic account records and artifacts were removed.

The final [Cloud Build smoke run](https://console.cloud.google.com/cloud-build/builds/ac2e73dc-440f-4e52-89fd-cd2ff2b0f2e1?project=817628492067) passed for release `edb5a9dd7f2a8184fe35` (implementation source `fb1279d`). The release is deployed in development. Post-deployment full-build and private PDF-preview probes passed, including actual artifact reads and removal of synthetic accounts/files. Public health/catalog requests returned 200; unauthenticated account, build and validation requests returned 401.

Container verification runs the actual unprivileged worker with a private writable SQLite database. It validates every bundled preset, tests canonical settings round trips, constructs both ASGI applications, and generates all output formats before permitting image promotion.

## Current launch boundary

Dedicated projects `opensiddur-builder-dev` and `opensiddur-builder-prod` have separate foundations, private remote state, GitHub deployment identities and budget alerts. Only development has runtime services. Public submissions remain disabled; production has no operator allowlist.

Firebase activation remains incomplete. The add-Firebase operation returned 403 despite the required IAM permissions being present; the Firebase project lookup returns 404. The operator must sign in to [Firebase Console](https://console.firebase.google.com/), accept any required account terms, and add the existing GCP projects. Then rerun the foundation scripts so Terraform adopts the project/default Hosting site and provisions the web app, authentication and browser database rules. The CLI cannot resolve account-level terms acceptance.

No public Hosting release or completed browser sign-in/account acceptance test is claimed. Google OAuth client configuration, production App Check registration, and finalized worldwide privacy/controller details remain launch prerequisites. See [deployment instructions](deployment.md) and [privacy responsibilities](privacy.md).

Complete the browser acceptance pass after activation: email-link sign-in, explicit consent, automatic HTML and manual PDF samples, full build, private downloads, share rotation/revocation, saved preset/logo reuse, account export, consent withdrawal and deletion. Public anonymous browsing must still work without consent; protected endpoints must reject unauthenticated access and other owners' UUIDs.
