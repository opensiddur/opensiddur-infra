"""Durable build state machine, admission reservations, and concurrency limits."""

import hashlib
import time
import uuid
from datetime import datetime, timezone

from .progress import build_steps

TERMINAL = {"succeeded", "partial", "failed", "cancelled", "expired"}
LIMITS = {
    "full": (5, 10800, 10800, 36000),
    "html": (300, 30, 1200, 3600),
    "pdf": (10, 300, 1200, 3600),
}


class Rejected(Exception):
    def __init__(self, message, status=429):
        super().__init__(message)
        self.status = status


class Builds:
    def __init__(self, store, release, clock=time.time):
        self.store, self.release, self.clock = store, release, clock

    def submit(self, owner, settings, formats, kind, idempotency, asset=None):
        if kind not in LIMITS:
            raise Rejected("Unknown build type", 422)
        now = self.clock()
        day = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d")
        group = "full" if kind == "full" else "preview"
        count_limit, seconds, user_seconds, global_seconds = LIMITS[kind]
        identifier = str(uuid.uuid4())
        payload = {
            "settings": settings,
            "formats": formats,
            "kind": kind,
            "asset": asset,
            "release": self.release,
        }
        digest = hashlib.sha256(
            __import__("json").dumps(payload, sort_keys=True).encode()
        ).hexdigest()
        idem_key = (
            "idempotency:"
            + hashlib.sha256(f"{owner}:{idempotency}".encode()).hexdigest()
        )
        user_key, global_key = (
            f"quota:{owner}:{day}:{group}",
            f"quota:global:{day}:{group}",
        )
        account_key, build_key = f"account:{owner}", f"build:{identifier}"

        def admit(values):
            if values[idem_key]:
                if values[idem_key]["digest"] != digest:
                    raise Rejected(
                        "Idempotency key already used for different settings", 409
                    )
                return values[idem_key]["build"]
            account = values[account_key]
            if not account or not account.get("enabled") or not account.get("consent"):
                raise Rejected("Consent is required before hosted processing", 403)
            if account.get(f"active_{group}"):
                raise Rejected("An operation is already outstanding", 409)
            user = values[user_key] or {
                "kind": "quota",
                "owner": owner,
                "counts": {},
                "seconds": 0,
                "expires": now + 32 * 86400,
            }
            glob = values[global_key] or {
                "kind": "quota",
                "counts": {},
                "seconds": 0,
                "expires": now + 32 * 86400,
            }
            if user["counts"].get(kind, 0) >= count_limit:
                raise Rejected("Daily operation limit reached")
            available = min(
                seconds,
                user_seconds - user["seconds"],
                global_seconds - glob["seconds"],
            )
            if available < (60 if kind == "full" else 5):
                raise Rejected("Daily runtime allowance is reserved or exhausted")
            if kind != "full":
                recent = [t for t in user.get("recent", []) if t > now - 60]
                if len(recent) >= 20:
                    raise Rejected("Preview rate limit reached")
                user["recent"] = [*recent, now]
            for quota in (user, glob):
                quota["seconds"] += available
                quota["counts"][kind] = quota["counts"].get(kind, 0) + 1
            user["key"], glob["key"] = user_key, global_key
            account[f"active_{group}"] = identifier
            build = {
                "kind": "build",
                "id": identifier,
                "owner": owner,
                "type": kind,
                "release": self.release,
                "settings": settings,
                "formats": formats,
                "asset": asset,
                "state": "queued",
                "stage": "queued",
                "steps": build_steps(kind, formats),
                "created": now,
                "deadline": now + 86400,
                "seconds": available,
                "group": group,
                "user_quota": user_key,
                "global_quota": global_key,
                "artifacts": [],
                "results": {},
                "cancel": False,
                "dispatch": None,
            }
            values.update(
                {
                    account_key: account,
                    build_key: build,
                    user_key: user,
                    global_key: glob,
                    idem_key: {
                        "kind": "idempotency",
                        "owner": owner,
                        "build": identifier,
                        "digest": digest,
                        "key": idem_key,
                        "expires": now + 31 * 86400,
                    },
                }
            )
            return identifier

        result = self.store.atomic(
            [idem_key, user_key, global_key, account_key, build_key], admit
        )
        return self.get(owner, result)

    def get(self, owner, identifier):
        build = self.store.get(f"build:{identifier}")
        if not build or build["owner"] != owner:
            raise Rejected("Build not found", 404)
        if build.get("expires", float("inf")) <= self.clock():
            raise Rejected("Build expired", 410)
        return build

    def claim(self, identifier, execution):
        key = f"build:{identifier}"
        build = self.store.get(key)
        if not build:
            return None
        slot_key = f"slots:{build['group']}"
        now = self.clock()

        def claim(values):
            row = values[key]
            if not row or row["state"] in TERMINAL or row["cancel"]:
                return None
            if row.get("started"):
                return None
            slots = values[slot_key] or {"kind": "slots", "ids": []}
            if len(slots["ids"]) >= 2:
                raise Rejected("Worker capacity busy", 503)
            slots["ids"].append(identifier)
            row.update(state="running", started=now, heartbeat=now, execution=execution)
            values[key], values[slot_key] = row, slots
            return row

        return self.store.atomic([key, slot_key], claim)

    def update(self, identifier, **fields):
        key = f"build:{identifier}"

        def update(values):
            row = values[key]
            if not row or row["state"] in TERMINAL or row["cancel"]:
                return False
            row.update(fields, heartbeat=self.clock())
            return True

        return self.store.atomic([key], update)

    def finish(self, identifier, state, results=None, artifacts=None):
        key = f"build:{identifier}"
        build = self.store.get(key)
        if not build:
            return
        account_key = f"account:{build['owner']}"
        slot_key = f"slots:{build['group']}"
        keys = [key, account_key, slot_key, build["user_quota"], build["global_quota"]]
        now = self.clock()

        def finish(values):
            row = values[key]
            if not row or row["state"] in TERMINAL:
                return
            elapsed = (
                min(row["seconds"], max(0, now - row["started"]))
                if row.get("started")
                else 0
            )
            refund = row["seconds"] - elapsed
            for quota_key in (row["user_quota"], row["global_quota"]):
                if values[quota_key]:
                    values[quota_key]["seconds"] = max(
                        0, values[quota_key]["seconds"] - refund
                    )
            if (
                values[account_key]
                and values[account_key].get(f"active_{row['group']}") == identifier
            ):
                values[account_key][f"active_{row['group']}"] = None
            if values[slot_key]:
                values[slot_key]["ids"] = [
                    x for x in values[slot_key]["ids"] if x != identifier
                ]
            for step in row.get("steps", []):
                if step["state"] == "running":
                    step["state"] = "cancelled" if row["cancel"] else "failed"
                elif step["state"] == "pending":
                    step["state"] = "skipped"
            row.update(
                state="cancelled" if row["cancel"] else state,
                stage="finished",
                finished=now,
                expires=now + (30 * 86400 if row["type"] == "full" else 86400),
                results=results or {},
                artifacts=[]
                if row["cancel"] or row.get("deleted")
                else (
                    artifacts
                    if artifacts is not None
                    else [
                        item
                        for item in row.get("artifacts", [])
                        if item["name"].endswith((".log", ".blg"))
                    ]
                ),
                elapsed=elapsed,
            )
            if row.get("deleted"):
                row["expires"] = now

        self.store.atomic(keys, finish)

    def cancel(self, owner, identifier):
        build = self.get(owner, identifier)
        key = f"build:{identifier}"

        def cancel(values):
            if values[key]["state"] not in TERMINAL:
                values[key]["cancel"] = True

        self.store.atomic([key], cancel)
        if not build.get("started"):
            self.finish(identifier, "cancelled")
        return self.get(owner, identifier)

    def share(self, owner, identifier, enabled):
        build = self.get(owner, identifier)
        if build["type"] != "full" or build["state"] not in {"succeeded", "partial"}:
            raise Rejected("Only finished builds can be shared", 409)
        token = str(uuid.uuid4()) if enabled else None
        digest = hashlib.sha256(token.encode()).hexdigest() if token else None
        key = f"build:{identifier}"
        old = build.get("share_hash")
        keys = (
            [key]
            + ([f"share:{old}"] if old else [])
            + ([f"share:{digest}"] if digest else [])
        )

        def share(values):
            if old:
                values[f"share:{old}"] = None
            values[key]["share_hash"] = digest
            if digest:
                values[f"share:{digest}"] = {
                    "kind": "share",
                    "owner": owner,
                    "build": identifier,
                    "expires": build["expires"],
                }

        self.store.atomic(keys, share)
        return token

    def shared(self, token):
        row = self.store.get("share:" + hashlib.sha256(token.encode()).hexdigest())
        if not row or row["expires"] <= self.clock():
            raise Rejected("Share not found", 404)
        return self.get(row["owner"], row["build"])
