# Deploy, update, roll back, or remove the builder

## Prerequisites

Use a current authenticated `gcloud` CLI, uv, Node 24/npm, and Terraform 1.13.5. The local operator needs permission to create projects, attach the selected billing account, enable services, manage project IAM, and provision Firebase, Firestore, Cloud Run, Cloud Tasks, Scheduler, buckets and Artifact Registry. These bootstrap privileges are separate from end-user accounts.

The default project IDs are `opensiddur-builder-dev` and `opensiddur-builder-prod`; override `PROJECT_ID`, `REGION`, and `STATE_BUCKET` for another installation. Every command uses an explicit project; it never changes your global gcloud project. Review the Terraform plan before applying. Set `TF_CLI_ARGS_apply=-auto-approve` only for an already reviewed unattended deployment.

## Foundation

```bash
export BILLING_ACCOUNT=YOUR_BILLING_ACCOUNT_ID
bash scripts/bootstrap.sh dev
bash scripts/bootstrap.sh prod
```

Bootstrap creates missing projects, links billing, and creates a private, versioned state bucket outside the main stack. Terraform then provisions the application foundation. Generated environment configuration is in `.runtime/<environment>.auto.tfvars` and is ignored by Git. Terraform working data is isolated per environment under `.runtime/terraform-dev` and `.runtime/terraform-prod`, preventing backend selection from crossing environments in one checkout. Record this configuration in a secure operations location. Set `billing_account` there to enable $10/$25/$50 project budget alerts; budgets are notifications, not spending caps.

Before direct Terraform state/output/plan/apply commands, select the environment with `source scripts/common.sh dev` (or `prod`) and run `tf_init`. The wrapper scripts do this automatically.

The state bucket may contain sensitive OAuth configuration; restrict access. Do not commit it or Terraform plans/state.

## Deploy application images and website

```bash
export PRIVACY_OPERATOR='Legal controller name'
export PRIVACY_CONTACT='privacy@example.org'
export GOOGLE_AUTH_ENABLED=false
# Production: configure App Check and provide the public site key.
export APP_CHECK_SITE_KEY='YOUR_RECAPTCHA_ENTERPRISE_SITE_KEY'
bash scripts/deploy.sh dev
```

The script runs unit tests and frontend build, assembles license notices, builds images with Cloud Build, validates every bundled preset and produces demo PDF/HTML, resolves immutable image digests, applies the runtime stack, publishes Firebase Hosting, and checks health. A failed container smoke test prevents promotion. The infra lock controls shared Python dependencies; the upstream lock supplies additional processor packages. Package compatibility and ASGI app construction are checked before export smoke tests. Build logs and source archives are retained in the managed build bucket for 30 days.

Use the [release procedure](../RELEASE_PROCEDURE.md) to deploy a tagged version to production. The first public launch requires an operator pilot, App Check, and the approved privacy notice; tagging the release is its approval.

Upstream commits are exact hashes, found when a deployment runs (`scripts/upstream.py`). Development, unless it is a release's development stage, uses the `main` heads of opensiddur-processor and opensiddur-projects. A release, in every stage, and production use their newest published, full releases; a release run resolves them once and every stage checks them. A local image build (without `deploy.sh`) needs `python3 scripts/upstream.py choose dev` (the main branches) or `choose prod` (the newest releases) first; `fetch_sources.py` prints the pins it uses. The job and preview services are versioned by a content hash covering application code, lockfiles and upstream references. Existing worker services/job definitions are retained in `release_images`, preserving queued jobs across updates. Keep images and definitions needed by outstanding work. Delete inactive versions only after confirming no queued/running build references them.

## Authentication

Firebase email-link sign-in is provisioned without application passwords. Complete the default email template, sender/support information, and authorized-domain setup in Firebase Console. Billing must be enabled for useful email-link quotas.

To enable Google sign-in, obtain the web OAuth client configuration from the project's Firebase/Google Cloud console. Set `google_client_id` and `google_client_secret` in private environment configuration, reapply Terraform, and deploy Hosting with `GOOGLE_AUTH_ENABLED=true`. Never put the client secret in the frontend or source repository. Signing in with two methods is linked explicitly by the signed-in user; email matching is not an account-merging policy.

For production App Check, register the Firebase web app with a reCAPTCHA Enterprise key restricted to the deployed domains, configure that key in Firebase App Check, and pass `APP_CHECK_SITE_KEY` when deploying. Keep `require_app_check=true`. Development may disable App Check while compute is restricted to configured operator emails.

Internal account UUIDs are independent of Firebase UIDs. Token verification and provider deletion are implemented behind the verifier interface. A future OIDC adapter must validate issuer/audience/signature/expiry and map `(issuer, subject)` to that same internal account. Do not migrate ownership or quota records to provider IDs.

## GitHub deployment

Terraform creates a GitHub OIDC trust restricted to this repository and `refs/heads/main`. Configure GitHub `dev` and `prod` environments, without required reviewers: the scheduled jobs deploy to them unattended, and reviewers would pause them. `dev` and `prod` need:

- Variables: `WIF_PROVIDER`, `DEPLOY_SERVICE_ACCOUNT`, `PRIVACY_OPERATOR`, `PRIVACY_CONTACT`, `PRIVACY_READY`, `APP_CHECK_SITE_KEY`, `GOOGLE_AUTH_ENABLED`.
- Secret: `DEPLOY_CONFIG`, containing the private environment tfvars (without image coordinates; release history is recovered from the private state bucket).

Get the provider and deployment identity with `terraform output`. Run the `Deploy` workflow from main to redeploy development at once. `Keep development current` runs on every merge to `main` (except documentation-only changes) and daily, and redeploys development whenever infra `main` or the `main` branch of opensiddur-processor or opensiddur-projects has moved since its last deployment. `Keep production current` runs daily and redeploys the latest Builder release, once it has been launched to the public, whenever opensiddur-processor or opensiddur-projects has published a newer full release. Each deployment records what it ran in `deployments/development.json` or `deployments/production.json` in its state bucket. Smoke-tested images are recorded per version and runtime ID under `deployments/versions/<tag>/images/`. Runtime promotion uses an explicit Terraform target list in `scripts/runtime-targets.sh`, excluding foundation/IAM/billing resources; full reconciliation is the bootstrap command. IAM/bootstrap changes require the local privileged operator; the GitHub deployment identity is for existing-stack runtime updates. If a Terraform foundation change requires an additional privilege, apply that change locally rather than expanding the trust indiscriminately.

## Observe and intervene

The UI polls build state every 10 seconds. Scheduler reconciles queued/stuck jobs and expiration each minute. Use Cloud Run execution status and the build UUID for diagnostics. Compiler logs remain in temporary local directories; they are not sent to Cloud Logging. Share-token request URLs are excluded from stored Cloud Run request logs. Default application logs have 30-day retention; Google-required audit logs follow provider policy.

Pause new work by setting `submissions_enabled=false` and clearing `admin_emails`, then redeploy. In production, first stop the daily upstream updates, which reopen admissions when they redeploy: write a reason to `gs://opensiddur-builder-prod-tfstate/deployments/production-paused` (see the release procedure's rollback section), and delete it to resume. For an immediate queue stop:

```bash
gcloud tasks queues pause builder --location=us-central1 --project=opensiddur-builder-prod
gcloud tasks queues pause previews --location=us-central1 --project=opensiddur-builder-prod
```

Runtime allowances reserve up to the remaining daily budget before admitting work, then refund unused seconds. This may temporarily reject admission while other builds reserve capacity. Existing per-user concurrency limits and site concurrency are enforced transactionally. An account gets at most five full builds and three runtime-hours per UTC admission day. Site full-build allowance is ten hours/day. Retry infrastructure dispatch; expensive worker execution has automatic retries disabled.

## Rollback

Restore a previously deployed `image`, `api_image`, and `release_id` in private environment configuration while preserving the complete `release_images` map, then apply Terraform. Redeploy the matching frontend from that Git commit with `scripts/hosting_config.py` and `scripts/deploy_hosting.py`. Do not rebuild mutable upstream branches. Existing executions continue against their pinned worker versions.

## Undeploy without deleting user data

```bash
bash scripts/undeploy.sh dev
```

This removes compute and maintenance resources and pauses queues, preserving authentication, presets, artifacts, registries, and Terraform state. Run it in a maintenance window; cancel/drain executions first. While cleanup is offline, app-level expiration is not served; bucket lifecycle still removes old build objects. Re-deployment resumes queues and cleanup. Storage/image charges continue for retained data.

## Irreversible data purge

```bash
CONFIRM_PURGE=opensiddur-builder-dev bash scripts/undeploy.sh dev purge
```

Purge stops compute, deletes Firebase authentication accounts, disables database deletion protection, empties managed buckets, and destroys Terraform-managed application resources. It never targets the pre-existing `opensiddur-client` project or resources outside the selected environment.

For complete removal, separately remove the protected state bucket including all object versions, then delete the dedicated project:

```bash
gcloud storage rm --all-versions --recursive gs://opensiddur-builder-dev-tfstate
gcloud projects delete opensiddur-builder-dev
```

Both commands are destructive. Project deletion and provider backup/log erasure follow Google's recovery and retention policies. Removing an environment does not delete the GitHub repository or local worktrees.

For a scripted complete teardown of a dedicated project (including state), use:

```bash
CONFIRM_PURGE=opensiddur-builder-dev CONFIRM_PROJECT_DELETE=opensiddur-builder-dev bash scripts/destroy-project.sh dev
```

Do not point complete-project teardown at a shared/pre-existing project. The two matching confirmations are mandatory, and no teardown is run automatically during deployment.

## Verify the live worker paths

Run opt-in probes against development with the actual Terraform outputs and deployed release ID:

```bash
uv run python tests/cloud_probe.py --project opensiddur-builder-dev --release RELEASE_ID --api API_URL --preview PREVIEW_URL
uv run python tests/cloud_probe.py --project opensiddur-builder-dev --release RELEASE_ID --api API_URL --preview PREVIEW_URL --type html
uv run python tests/cloud_probe.py --project opensiddur-builder-dev --release RELEASE_ID --api API_URL --preview PREVIEW_URL --type pdf
```

These use the local gcloud operator credentials to enqueue synthetic records, then exercise Cloud Tasks OIDC, API dispatch, the private service/job, Firestore and Storage. They remove their test records/files, preserve truthful global runtime accounting, and never create a real authentication identity or send email. They do **not** replace browser/sign-in acceptance testing, which requires Firebase activation and provider configuration.

### Account export/deletion rollout and retention gate

Run `python3 scripts/check_retention.py` and `terraform -chdir=infrastructure test`
for local policy verification. Deployment also runs
`uv run python scripts/check_retention.py --live "$PROJECT_ID"` before promotion.
The live audit inventories all Firestore backups and schedules, PITR, project
buckets, artifact soft deletion/versioning/lifecycles, and default log retention.
The deployment identity needs `logging.buckets.get` to inspect log retention;
the dedicated `builderRetentionAuditor` role grants only that configuration read,
without access to log entries. Apply its Terraform role and deployer binding
as a foundation change before enabling this gate in an existing environment.
Unknown backups or buckets fail closed and need a user-data/restore review; the
protected `-tfstate` bucket is configuration-only and must never contain user data.
Provider-required audit records are outside this operator-controlled policy.

Existing installations have a 31-day artifact lifecycle rule. An infrastructure
operator must apply the reviewed foundation changes for artifact/build buckets and
the Firestore recovery setting before the runtime deployment gate can pass. The
runtime deployment deliberately does not apply privileged foundation changes.
Maintenance migrates old quota/idempotency expiration values down by two/one days,
once, preserving their original age rather than starting retention over.

The runtime deploy includes `builder-account-data`, using the API image/service
identity, with an enforced one-hour timeout. Maintenance retries durable data
operations independently of compiler quotas. Search error logs for
`Account cleanup requires retry` to investigate stalled cleanup without logging
account identifiers or provider error payloads. Do not delete unfinished operation
records: they retain the locators needed to finish erasure.

Before production promotion, run:

```
uv run python tests/account_data_cloud_probe.py --project opensiddur-builder-dev
```

This opt-in probe creates two synthetic Firebase users and matching Firestore/files,
exports one through production adapters, erases it, verifies the other survives,
and removes its own data/receipts in a finally block. It exercises service logic
locally against development stores; it does not claim Cloud Run or browser coverage.
After deploying the new development image, additionally smoke-test API start/status,
Cloud Scheduler → account-data job dispatch, ZIP download, typed confirmation,
Google/email reauthentication, and deletion progress across a browser reload.
