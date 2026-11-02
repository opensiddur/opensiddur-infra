import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    project: str = os.getenv("GOOGLE_CLOUD_PROJECT", "")
    region: str = os.getenv("REGION", "us-central1")
    bucket: str = os.getenv("ARTIFACT_BUCKET", "")
    release: str = os.getenv("RELEASE_ID", "development")
    bundle: str = os.getenv("BUNDLE_DIR", "/opt/bundle")
    processor: str = os.getenv("PROCESSOR_DIR", "/opt/processor")
    api_url: str = os.getenv("API_URL", "")
    audience: str = os.getenv(
        "INTERNAL_AUDIENCE", "https://opensiddur-builder/internal"
    )
    dispatcher_email: str = os.getenv("DISPATCHER_EMAIL", "")
    worker_email: str = os.getenv("WORKER_EMAIL", "")
    preview_url: str = os.getenv("PREVIEW_URL", "")
    queue: str = os.getenv("TASK_QUEUE", "builder")
    job: str = os.getenv("BUILD_JOB", "")
    enabled: bool = os.getenv("SUBMISSIONS_ENABLED", "false").lower() == "true"
    app_check: bool = os.getenv("REQUIRE_APP_CHECK", "true").lower() == "true"
    admins: tuple[str, ...] = tuple(
        filter(None, os.getenv("ADMIN_EMAILS", "").split(","))
    )
    consent_version: str = os.getenv("CONSENT_VERSION", "2026-11-01")
