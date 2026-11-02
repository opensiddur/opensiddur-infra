"""Opt-in synthetic integration probe. Run explicitly; never collected by pytest."""

import argparse
import json
import subprocess
import time
import uuid
from dataclasses import replace

from google.cloud import run_v2, tasks_v2
from google.oauth2.credentials import Credentials

from opensiddur_infra.builds import Builds, TERMINAL
from opensiddur_infra.config import Config
from opensiddur_infra.storage import Storage
from opensiddur_infra.store import FirestoreStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("project", "release", "api", "preview"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--type", choices=["full", "html", "pdf"], default="full")
    args = parser.parse_args()
    token = subprocess.check_output(
        ["gcloud", "auth", "print-access-token"], text=True
    ).strip()
    credentials = Credentials(token)
    config = replace(
        Config(),
        project=args.project,
        release=args.release,
        bucket=args.project + "-artifacts",
    )
    store = FirestoreStore(args.project, credentials=credentials)
    storage = Storage(config, credentials=credentials)
    owner = str(uuid.uuid4())
    key = "account:" + owner
    store.atomic(
        [key],
        lambda rows: rows.update(
            {
                key: {
                    "kind": "account",
                    "owner": owner,
                    "id": owner,
                    "enabled": True,
                    "consent": {"version": "synthetic integration test"},
                }
            }
        ),
    )
    builds = Builds(store, args.release)
    settings = {
        "book": {"project": "infra_demo", "file_name": "index.xml"},
        "priority": {"transclusion": ["tanakh-wlc-he"]},
        "distribution": {"notice": "none", "back_notice": "none"},
    }
    row = builds.submit(
        owner, settings, ["pdf", "html", "tex", "xml"], args.type, str(uuid.uuid4())
    )
    build_key = "build:" + row["id"]
    store.atomic(
        [build_key],
        lambda rows: rows[build_key].update(
            job=f"projects/{args.project}/locations/us-central1/jobs/builder-{args.release}",
            preview_url=args.preview,
        ),
    )
    client = tasks_v2.CloudTasksClient(credentials=credentials)
    parent = client.queue_path(args.project, "us-central1", "builder")
    print("Synthetic build:", row["id"], flush=True)
    try:
        client.create_task(
            parent=parent,
            task={
                "http_request": {
                    "http_method": tasks_v2.HttpMethod.POST,
                    "url": args.api + "/internal/dispatch",
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"id": row["id"]}).encode(),
                    "oidc_token": {
                        "service_account_email": f"builder-dispatcher@{args.project}.iam.gserviceaccount.com",
                        "audience": config.audience,
                    },
                }
            },
        )
        for _ in range(240):
            row = builds.get(owner, row["id"])
            if row["state"] in TERMINAL:
                break
            time.sleep(2)
        else:
            raise RuntimeError("Cloud integration probe timed out")
        assert row["state"] == "succeeded", row["results"]
        for artifact in row["artifacts"]:
            data = storage.read(artifact["object"])
            assert len(data) == artifact["size"]
            if artifact["name"] == "book.pdf":
                assert data.startswith(b"%PDF")
        print(
            "Cloud Tasks → API OIDC → worker → Firestore → Storage passed", flush=True
        )
    finally:
        current = store.get(build_key)
        if current and current["state"] not in TERMINAL:
            builds.cancel(owner, row["id"])
            if current.get("execution") and args.type == "full":
                run_v2.ExecutionsClient(credentials=credentials).cancel_execution(
                    name=current["job"] + "/executions/" + current["execution"]
                )
            for _ in range(60):
                if store.get(build_key)["state"] in TERMINAL:
                    break
                time.sleep(2)
            else:
                raise RuntimeError(
                    "Cancellation not confirmed; synthetic records retained for reconciliation"
                )
        storage.delete_prefix("builds/" + row["id"] + "/")
        documents = [build_key, key, row["user_quota"]]
        documents += [entry["key"] for entry in store.list("idempotency", owner)]
        for document in documents:
            store.atomic(
                [document],
                lambda values, document=document: values.update({document: None}),
            )
        print("Synthetic account and artifacts removed", flush=True)


if __name__ == "__main__":
    main()
