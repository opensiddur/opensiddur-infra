import time

from .builds import TERMINAL


def reconcile(config, store, builds, storage, dispatcher):
    now = time.time()
    counts = {"queued": 0, "expired": 0, "reconciled": 0}
    records = store.list("build", filters={"state": ("in", ["queued", "running"])})
    records += store.list("build", filters={"expires": ("<=", now)})
    records = list({row["id"]: row for row in records}.values())
    for row in records:
        identifier = row["id"]
        if row["state"] == "queued" and not row.get("cancel"):
            if now > row["deadline"]:
                builds.finish(
                    identifier,
                    "failed",
                    {"build": {"message": "Queue deadline exceeded"}},
                )
            else:
                # Call launch directly after a stale dispatch: named Cloud Tasks have deduplication tombstones.
                if row.get("dispatch") and now - row["dispatch"] > 180:
                    dispatcher.launch(row)
                    builds.update(identifier, dispatch=now)
                elif not row.get("dispatch"):
                    dispatcher.enqueue(identifier)
                counts["queued"] += 1
        elif row["state"] == "running":
            if row["type"] == "full":
                from google.cloud import run_v2

                execution = row.get("execution", "")
                job = row.get("job") or config.job
                name = f"{job.rsplit('/jobs/', 1)[0]}/jobs/{job.rsplit('/', 1)[-1]}/executions/{execution}"
                result = run_v2.ExecutionsClient().get_execution(name=name)
                if result.completion_time:
                    builds.finish(
                        identifier,
                        "failed",
                        {
                            "build": {
                                "message": "Execution terminated before publishing results"
                            }
                        },
                    )
                    counts["reconciled"] += 1
                elif row.get("cancel"):
                    run_v2.ExecutionsClient().cancel_execution(name=name)
            elif now - row.get("heartbeat", row["started"]) > row["seconds"] + 60:
                builds.finish(
                    identifier,
                    "failed",
                    {"build": {"message": "Preview execution expired"}},
                )
        row = store.get(f"build:{identifier}")
        if row and row["state"] in TERMINAL and row.get("expires", float("inf")) <= now:
            storage.delete_prefix(f"builds/{identifier}/")
            keys = [f"build:{identifier}"]
            if row.get("share_hash"):
                keys.append(f"share:{row['share_hash']}")
            store.atomic(
                keys, lambda values: values.update({key: None for key in keys})
            )
            counts["expired"] += 1
    housekeeping = store.get("maintenance:hourly") or {"last": 0}
    if now - housekeeping["last"] < 3600:
        return counts
    store.atomic(
        ["maintenance:hourly"],
        lambda rows: rows.update(
            {"maintenance:hourly": {"kind": "maintenance", "last": now}}
        ),
    )
    references = {r.get("asset") for r in store.list("preset")}
    references |= {r.get("asset") for r in store.list("build")}
    for asset in store.list("asset"):
        if asset["id"] not in references and asset["created"] < now - 86400:
            storage.delete_prefix(f"assets/{asset['id']}/")
            key = f"asset:{asset['id']}"
            store.atomic([key], lambda values: values.update({key: None}))
    for quota in store.list("quota"):
        if quota.get("expires", float("inf")) < now:
            # Quota records carry their deterministic keys for removal.
            key = quota.get("key")
            if key:
                store.atomic([key], lambda values, key=key: values.update({key: None}))
    for entry in store.list("idempotency"):
        if entry["expires"] < now:
            # Identity-independent key is retained in the record for deterministic cleanup.
            if entry.get("key"):
                store.atomic(
                    [entry["key"]], lambda values: values.update({entry["key"]: None})
                )
    return counts
