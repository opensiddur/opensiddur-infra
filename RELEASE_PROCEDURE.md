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
3. Review the preview fixture and font pack pins. opensiddur-processor and
   opensiddur-projects are not pinned here: the release builds with their newest
   full releases, and production takes their later releases daily
   (`Keep production current`). Release builds use the tagged lockfiles.
4. From the candidate checkout run `python3 scripts/release_notes.py vX.Y.Z`
   with Python 3.11 or newer to preview the notes and validate versions.
   Merge the PR after the normal checks pass.

## Configure production before the first release

Use the existing `opensiddur-builder-prod` foundation and
`https://opensiddur-builder-prod.web.app`. Confirm billing and quotas,
Firebase Hosting and Auth, Cloud Build, Cloud Run and the Terraform state
backend are ready. Follow [the deployment guide](docs/deployment.md) for
foundation setup and the separate GitHub environments.

- In GitHub, restrict the `prod` environment's deployments to `main`, without
  required reviewers: running the release workflow is the decision to deploy,
  and the daily production job must run unattended. Create a `prod-launch`
  environment with required reviewers who can confirm the production
  acceptance checks, and disable administrator bypass; a first public launch
  waits on it between the pilot and opening admissions. Keep Workload Identity
  Federation restricted to `refs/heads/main`.
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
tag and GitHub Release, then deploys to production. The production build uses
that same commit, lockfiles and upstream releases, builds and smoke-tests images
in its own project, and deploys the recorded digests.

On the first release, the pilot job deploys with admissions closed, and the
`launch-approval` job then waits on the `prod-launch` reviewers. Before
approving it, use a named operator to sign in by email,
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
re-run the failed jobs of the original run: that keeps the upstream releases it
resolved and reuses any smoke-tested production images recorded for them. Running
**Release Builder** with operation `retry-production` and the published tag also
works, but it resolves the newest upstream releases again, so after a new
upstream release it builds and deploys a combination development never ran.
A pilot is refused for a version that is already public, since it would close
admissions; a first launch whose public step failed can retry with its pilot.

Before rolling back or pausing production, stop its daily upstream updates, which
would otherwise redeploy the latest release with admissions open:

```bash
echo "Rolled back to vX.Y.Z: reason" |
  gcloud storage cp - gs://opensiddur-builder-prod-tfstate/deployments/production-paused
```

Delete that object to resume them. To roll back a Builder release, read the
previous tag’s `public.json` from the production state bucket; to roll back an
upstream update of the same release, read the earlier record under
`versions/<tag>/public/<runtime ID>.json`. Review a Terraform plan using its
`worker_image`, `api_image` and `release` as `image`, `api_image` and
`release_id`. Load the complete release
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
