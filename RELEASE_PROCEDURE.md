# Open Siddur Builder release procedure

Builder code releases use annotated `vX.Y.Z` tags. Use a patch for fixes, a
minor version for new features, and a major version for incompatible changes
after 1.0. The first release is `v0.1.0`. The version identifies the application
release. The runtime content ID identifies its bundled configuration and code
for workers and queued jobs.

## Prepare a release

1. Open a PR on `main` with a dated or undated `## [X.Y.Z]` section in
   `CHANGELOG.md`. Move the relevant entries from `[Unreleased]` and leave
   that section open for later changes.
2. Match the Python and frontend package versions. Run `uv lock` after
   editing `pyproject.toml`. In `web`, use
   `npm version X.Y.Z --no-git-tag-version` to update both frontend files.
   Version `0.1.0` is already set in both packages and lockfiles.
3. Review the processor, corpus, preview fixture and font pack pins. If a
   scheduled development promotion is ready to ship, review and commit its
   upstream lock changes in a PR. Release builds use the tagged lockfiles.
4. From the candidate checkout run `python3 scripts/release_notes.py vX.Y.Z`
   with Python 3.11 or newer to preview the notes and validate versions.
   Merge the PR after the normal checks pass.

## Configure production before the first release

Use the existing `opensiddur-builder-prod` foundation and
`https://opensiddur-builder-prod.web.app`. Confirm billing and quotas,
Firebase Hosting and Auth, Cloud Build, Cloud Run and the Terraform state
backend are ready. Follow [the deployment guide](docs/deployment.md) for
foundation setup and the separate GitHub environments.

- In GitHub, configure required reviewers on `prod`, restrict deployments
  to `main`, and disable administrator bypass. Select reviewers who can
  confirm the production acceptance checks. Keep Workload Identity Federation
  restricted to `refs/heads/main`.
- Configure production email-link sign-in, support and sender details, and
  authorize `opensiddur-builder-prod.web.app` in Firebase Auth. Register the
  production Firebase web app in App Check using a reCAPTCHA Enterprise key
  restricted to the production hostname. Set `APP_CHECK_SITE_KEY` in the
  `prod` environment and `GOOGLE_AUTH_ENABLED=false` for the first launch.
- Complete the [privacy launch review](docs/privacy.md). Set `PRIVACY_OPERATOR`,
  `PRIVACY_CONTACT`, and `APPROVED_PRIVACY_NOTICE` to the confirmed controller,
  contact, and complete approved plain-text notice. Set `PRIVACY_READY=true`
  only after that review. Keep these as production environment variables.
- Set `PILOT_OPERATORS` in the production environment secrets to a JSON array
  of named operator email addresses. Keep `require_app_check = true` and
  `submissions_enabled = false` in the baseline production `DEPLOY_CONFIG`.
  The deployment workflow controls admission explicitly.

## Cut and deploy the release

Run **Release Builder** from `main` with operation `release` and an explicit
tag. Enable **first public launch** for the first rollout. The workflow also
requires a pilot for `v0.1.0` even if the option is omitted.

The workflow tests and deploys the exact triggering commit to development.
Once development verifies the API and hosted bundle, it publishes the annotated
tag and GitHub Release. GitHub then requests production approval. The production
build uses that same commit and lockfiles, builds and smoke-tests images in its
own project, and deploys the recorded digests.

On the first release, approve the pilot job and wait for it to finish. Before
approving the separate public job, use a named operator to sign in by email,
give consent, generate HTML and PDF samples, and download a completed book.
Check that a non-operator cannot submit and that a consented operator request
without App Check receives HTTP 403. Check the privacy notice and confirm the
production domain and version. The public job verifies the staged Hosting
bundle and API before opening admissions. Afterwards, verify a signed-in
non-operator with valid App Check can submit and download a test build.

The API health endpoint reports the version, source commit, runtime ID and
admission status. The private state bucket retains the smoke-tested image
digests and deployment records under `deployments/versions/<tag>/`.
`pilot.json` and `public.json` identify the Firebase Hosting version and the
admission policy verified at deployment.

## Retry or roll back

If development fails, fix the issue and rerun the release. If tag creation
succeeded but publication failed, rerun the failed publish job at the same
commit. Never move a published tag. If production fails after publication,
run **Release Builder** from `main` with operation `retry-production` and
the published tag. This uses its original commit and reuses any recorded
smoke-tested production images. Retrying `v0.1.0` runs the pilot checks and
approval sequence again, which temporarily closes public admissions.

To roll back, read the previous tag’s `public.json` from the production state
bucket and review a Terraform plan using its `worker_image`, `api_image` and
`release` as `image`, `api_image` and `release_id`. Load the complete release
history with `scripts/deployment_history.py load` before planning. Use the
targets from `scripts/runtime-targets.sh` and keep App Check enabled. Set
`submissions_enabled=false` until the rollback is verified. Apply the plan,
then republish the matching Hosting version with
`uv run --frozen python scripts/deploy_hosting.py opensiddur-builder-prod HOSTING_VERSION`
using the full `sites/…/versions/…` value in the record. Check the live health,
frontend and authentication, then re-enable admissions with a targeted API
apply. Retain rollback images, Hosting versions and worker definitions while
needed. After the first launch, if there is no previous production release,
disable public admissions with a targeted API apply and use the queue pause
commands in the deployment guide if needed.
