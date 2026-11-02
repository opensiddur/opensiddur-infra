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

Bootstrap creates missing projects, links billing, and creates a private, versioned state bucket outside the main stack. Terraform then provisions the application foundation. Generated environment configuration is in `.runtime/<environment>.auto.tfvars` and is ignored by Git. Record this configuration in a secure operations location. Set `billing_account` there to enable $10/$25/$50 project budget alerts; budgets are notifications, not spending caps.

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

The script runs unit tests and frontend build, assembles license notices, builds images with Cloud Build, validates every bundled preset and produces demo PDF/HTML, resolves immutable image digests, applies the runtime stack, publishes Firebase Hosting, and checks health. A failed container smoke test prevents promotion. Build logs and source archives are retained in the managed build bucket for 30 days.

Run `scripts/deploy.sh prod` to deploy production after dev verification. Public submissions default off. Complete the privacy/legal tasks and authentication setup before setting `submissions_enabled = true` and `require_app_check = true` in the environment configuration.

The first deployment uses exact upstream commit hashes in `releases.lock.json`. The job and preview services are versioned by a content hash covering application code, lockfiles and upstream references. Existing worker services/job definitions are retained in `release_images`, preserving queued jobs across updates. Keep images and definitions needed by outstanding work. Delete inactive versions only after confirming no queued/running build references them.

## Authentication

Firebase email-link sign-in is provisioned without application passwords. Complete the default email template, sender/support information, and authorized-domain setup in Firebase Console. Billing must be enabled for useful email-link quotas.

To enable Google sign-in, obtain the web OAuth client configuration from the project's Firebase/Google Cloud console. Set `google_client_id` and `google_client_secret` in private environment configuration, reapply Terraform, and deploy Hosting with `GOOGLE_AUTH_ENABLED=true`. Never put the client secret in the frontend or source repository. Signing in with two methods is linked explicitly by the signed-in user; email matching is not an account-merging policy.

For production App Check, register the Firebase web app with a reCAPTCHA Enterprise key restricted to the deployed domains, configure that key in Firebase App Check, and pass `APP_CHECK_SITE_KEY` when deploying. Keep `require_app_check=true`. Development may disable App Check while compute is restricted to configured operator emails.

Internal account UUIDs are independent of Firebase UIDs. Token verification and provider deletion are implemented behind the verifier interface. A future OIDC adapter must validate issuer/audience/signature/expiry and map `(issuer, subject)` to that same internal account. Do not migrate ownership or quota records to provider IDs.

## GitHub deployment

Terraform creates a GitHub OIDC trust restricted to this repository and `refs/heads/main`. Configure GitHub `dev` and `prod` environments, with production reviewers:

- Variables: `WIF_PROVIDER`, `DEPLOY_SERVICE_ACCOUNT`, `PRIVACY_OPERATOR`, `PRIVACY_CONTACT`, `APP_CHECK_SITE_KEY`, `GOOGLE_AUTH_ENABLED`.
- Secret: `DEPLOY_CONFIG`, containing the private environment tfvars (without image coordinates; release history is recovered from the private state bucket).

Get provider and deployment identity with `terraform output`. Run the `Deploy` workflow from main. IAM/bootstrap changes require the local privileged operator; the GitHub deployment identity is for existing-stack runtime updates. If a Terraform foundation change requires an additional privilege, apply that change locally rather than expanding the trust indiscriminately.

## Observe and intervene

The UI polls build state every 10 seconds. Scheduler reconciles queued/stuck jobs and expiration each minute. Use Cloud Run execution status and the build UUID for diagnostics. Compiler logs remain in temporary local directories; they are not sent to Cloud Logging. Share-token request URLs are excluded from stored Cloud Run request logs. Default application logs have 30-day retention; Google-required audit logs follow provider policy.

Pause new work by setting `submissions_enabled=false` and clearing `admin_emails`, then redeploy. For an immediate queue stop:

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
