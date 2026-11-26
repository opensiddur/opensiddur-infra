"""Fail closed on recovery-policy drift. --live audits without changing resources."""

import argparse
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

MAX_SECONDS = 30 * 86400
ROOT = Path(__file__).resolve().parents[1]


def validate_plan(plan):
    """Validate resolved Terraform values, including future backup resources."""

    def visit(module):
        for resource in module.get("resources", []):
            kind, values = resource["type"], resource.get("values", {})
            if kind == "google_firestore_backup_schedule":
                if float(values.get("retention", "0s").rstrip("s")) > MAX_SECONDS:
                    raise ValueError("Firestore backup retention exceeds 30 days")
                raise ValueError(
                    "Backups require an erasure-aware restore design before enablement"
                )
            if kind == "google_firestore_database":
                if (
                    values.get("point_in_time_recovery_enablement")
                    != "POINT_IN_TIME_RECOVERY_DISABLED"
                ):
                    raise ValueError("Firestore PITR must remain disabled")
            if kind == "google_storage_bucket" and resource["name"] in {
                "artifacts",
                "builds",
            }:
                validate_bucket(values, terraform=True)
        for child in module.get("child_modules", []):
            visit(child)

    visit(plan.get("planned_values", {}).get("root_module", {}))


def validate_bucket(bucket, terraform=False):
    if terraform:
        versioning = (bucket.get("versioning") or [{}])[0]
        soft = (bucket.get("soft_delete_policy") or [{}])[0]
        soft_seconds = soft.get("retention_duration_seconds", 0)
        rules = bucket.get("lifecycle_rule", [])
        ages = [r.get("condition", [{}])[0].get("age") for r in rules]
    else:
        versioning = bucket.get("versioning", {})
        soft_seconds = bucket.get("softDeletePolicy", {}).get(
            "retentionDurationSeconds", 0
        )
        rules = bucket.get("lifecycle", {}).get("rule", [])
        ages = [r.get("condition", {}).get("age") for r in rules]
    if versioning.get("enabled") or int(soft_seconds):
        raise ValueError(
            "User storage versioning and soft deletion must remain disabled"
        )
    policy = bucket.get("retentionPolicy", {})
    if int(policy.get("retentionPeriod", 0)):
        raise ValueError("User storage retention locks prevent immediate erasure")
    if not rules or any(age is None or age > 30 for age in ages):
        raise ValueError("User storage lifecycle must delete within 30 days")


def validate_source(root=ROOT):
    main = (root / "infrastructure/main.tf").read_text()
    assert re.search(
        r'point_in_time_recovery_enablement\s*=\s*"POINT_IN_TIME_RECOVERY_DISABLED"',
        main,
    )
    assert main.count("versioning { enabled = false }") == 2
    assert main.count("soft_delete_policy { retention_duration_seconds = 0 }") == 2
    all_tf = "\n".join(p.read_text() for p in (root / "infrastructure").glob("*.tf"))
    assert not re.search(r"age\s*=\s*(3[1-9]|[4-9]\d|\d{3,})\b", all_tf)
    buckets = re.findall(r'resource\s+"google_storage_bucket"\s+"([^"]+)"', all_tf)
    assert sorted(buckets) == ["artifacts", "builds"], (
        "New storage needs an export/erasure and recovery review"
    )
    assert not re.search(r'resource\s+"[^"]*(?:backup|snapshot)[^"]*"', all_tf), (
        "Recovery mechanisms need erasure-aware design"
    )
    builds = (root / "app/opensiddur_infra/builds.py").read_text()
    assert not re.search(r"(?:31|32)\s*\*\s*86400", builds)
    assert "retention_days = 30" in (root / "infrastructure/privacy.tf").read_text()
    assert "30 days" in (root / "AGENTS.md").read_text()


def audit_live(project):
    # gcloud credentials stay in memory and never appear in output or command args.
    import requests

    token = subprocess.check_output(
        ["gcloud", "auth", "print-access-token"], text=True, timeout=30
    ).strip()
    session = requests.Session()
    session.headers.update(
        {"Authorization": "Bearer " + token, "X-Goog-User-Project": project}
    )

    def get(url):
        response = session.get(url, timeout=30)
        response.raise_for_status()
        return response.json()

    base = f"https://firestore.googleapis.com/v1/projects/{project}"
    databases = get(base + "/databases")
    for db in databases.get("databases", []):
        if db.get("pointInTimeRecoveryEnablement") != "POINT_IN_TIME_RECOVERY_DISABLED":
            raise ValueError("Live Firestore PITR drift")
        schedules = get(
            "https://firestore.googleapis.com/v1/" + db["name"] + "/backupSchedules"
        )
        if schedules.get("backupSchedules"):
            raise ValueError(
                "Unmanaged Firestore backup schedule; restore review required"
            )
    backups = get(base + "/locations/-/backups")
    if backups.get("unreachable"):
        raise ValueError("Could not audit all backup locations")
    if backups.get("backups"):
        for backup in backups["backups"]:
            start = datetime.fromisoformat(
                backup["snapshotTime"].replace("Z", "+00:00")
            )
            end = datetime.fromisoformat(backup["expireTime"].replace("Z", "+00:00"))
            if (end - start).total_seconds() > MAX_SECONDS:
                raise ValueError("Live backup retention exceeds 30 days")
        raise ValueError(
            "Unmanaged backups found; erasure-aware restore review required"
        )
    buckets, page = [], ""
    while True:
        response = get(
            f"https://storage.googleapis.com/storage/v1/b?project={project}&pageToken={page}"
        )
        buckets.extend(response.get("items", []))
        page = response.get("nextPageToken")
        if not page:
            break
    expected = {f"{project}-artifacts", f"{project}-builds"}
    for bucket in buckets:
        if bucket["name"] in expected:
            validate_bucket(bucket)
            expected.remove(bucket["name"])
        elif bucket["name"] != f"{project}-tfstate":
            raise ValueError("Unmanaged storage bucket; review for user recovery data")
    if expected:
        raise ValueError("Expected managed buckets missing")
    logging = get(
        f"https://logging.googleapis.com/v2/projects/{project}/locations/global/buckets/_Default"
    )
    if int(logging.get("retentionDays", 0)) > 30:
        raise ValueError("Operational log retention exceeds 30 days")
    print("Live recovery retention audit passed")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", metavar="PROJECT")
    parser.add_argument("--plan", type=Path)
    args = parser.parse_args()
    validate_source()
    if args.plan:
        validate_plan(json.loads(args.plan.read_text()))
    if args.live:
        audit_live(args.live)
    print("Recovery retention policy passed")


if __name__ == "__main__":
    main()
