"""Durable, retryable account exports and erasure. No user content goes in logs."""

import hashlib
import json
import logging
import os
import tempfile
import time
import uuid
import zipfile
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import PurePosixPath

from .builds import Rejected

DAY = 86400
LEASE = 3900  # Longer than the data job's enforced one-hour execution timeout.


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def enabled(store, owner):
    row = store.get(f"account:{owner}")
    return bool(row and row.get("enabled"))


@contextmanager
def writing(store, owner):
    """Fence bounded object writes against erasure, including in-flight API uploads."""
    key, account = f"activity:{uuid.uuid4()}", f"account:{owner}"

    def begin(rows):
        if not rows[account] or not rows[account].get("enabled"):
            raise Rejected("Account unavailable", 403)
        rows[key] = {
            "kind": "activity",
            "owner": owner,
            "key": key,
            "expires": time.time() + LEASE,
        }

    store.atomic([account, key], begin)
    try:
        yield
    finally:
        store.atomic([key], lambda rows: rows.update({key: None}))


class AccountStorage:
    """Every user object write is bounded and registered before it can begin."""

    def __init__(self, storage, store, owner):
        self.storage, self.store, self.owner = storage, store, owner

    def __getattr__(self, name):
        return getattr(self.storage, name)

    def put(self, name, *args, **kwargs):
        with writing(self.store, self.owner):
            result = self.storage.put(name, *args, **kwargs)
            if not enabled(self.store, self.owner):
                self.storage.delete_prefix(name)
                raise Rejected("Account unavailable", 403)
            return result


def json_bytes(value):
    def encode(item):
        if isinstance(item, (datetime, date)):
            return item.isoformat()
        raise TypeError(f"Unsupported export value: {type(item).__name__}")

    return json.dumps(value, ensure_ascii=False, indent=2, default=encode).encode()


def public_operation(row):
    return {k: row[k] for k in ("id", "state", "phase", "expires") if k in row}


class DataOperations:
    def __init__(self, store, storage, verifier, dispatcher):
        self.store, self.storage = store, storage
        self.verifier, self.dispatcher = verifier, dispatcher

    def start_export(self, owner, preferences):
        account_key, identifier = f"account:{owner}", str(uuid.uuid4())
        key = f"operation:{identifier}"
        existing = self.store.get(account_key) or {}
        old = existing.get("export")
        keys = [account_key, key] + ([f"operation:{old}"] if old else [])

        def begin(rows):
            account = rows[account_key]
            if not account or not account.get("enabled"):
                raise Rejected("Account unavailable", 403)
            # A concurrent request changes the account transaction and must retry
            # with the new operation key rather than creating a second export.
            if account.get("export") != old:
                raise Rejected("Export request changed; retry", 409)
            previous = rows.get(f"operation:{old}")
            if previous and previous["state"] in {"queued", "running"}:
                return previous
            row = {
                "kind": "operation",
                "id": identifier,
                "owner": owner,
                "type": "export",
                "state": "queued",
                "phase": "Preparing download",
                "created": time.time(),
                "preferences": preferences,
            }
            rows[key] = row
            account["export"] = identifier
            return row

        row = self.store.atomic(keys, begin)
        return public_operation(row)

    def start_delete(self, principal, receipt):
        owner = principal.account_id
        account_key, key = f"account:{owner}", f"operation:{uuid.uuid4()}"
        receipt_key = f"receipt:{digest(receipt)}"

        def begin(rows):
            account = rows[account_key]
            if not account:
                raise Rejected("Account unavailable", 401)
            if account.get("deletion"):
                if account.get("deletion_receipt") != digest(receipt):
                    raise Rejected("Deletion already in progress; use its receipt", 409)
                return
            account.update(
                enabled=False,
                consent=None,
                deletion=key.split(":")[1],
                deletion_receipt=digest(receipt),
            )
            rows[key] = {
                "kind": "operation",
                "id": key.split(":")[1],
                "owner": owner,
                "type": "delete",
                "state": "queued",
                "phase": "Blocking access",
                "created": time.time(),
                "receipt": digest(receipt),
            }
            rows[receipt_key] = {
                "kind": "receipt",
                "state": "queued",
                "phase": "Blocking access",
            }

        self.store.atomic([account_key, key, receipt_key], begin)
        return {"state": "queued"}

    def status(self, owner, identifier):
        row = self.store.get(f"operation:{identifier}")
        if (
            not enabled(self.store, owner)
            or not row
            or row.get("owner") != owner
            or row["type"] != "export"
        ):
            raise Rejected("Export not found", 404)
        if row.get("expires", float("inf")) <= time.time():
            raise Rejected("Export expired", 410)
        return row

    def receipt(self, token):
        row = self.store.get(f"receipt:{digest(token)}")
        if not row or row.get("expires", float("inf")) <= time.time():
            raise Rejected("Deletion status unavailable", 404)
        return {k: row[k] for k in ("state", "phase")}

    def progress(self, row, **fields):
        key = f"operation:{row['id']}"
        receipt_key = f"receipt:{row['receipt']}" if row.get("receipt") else None
        keys = [key] + ([receipt_key] if receipt_key else [])

        def update(rows):
            if rows[key]:
                rows[key].update(fields)
            if receipt_key and rows[receipt_key]:
                rows[receipt_key].update(
                    {k: v for k, v in fields.items() if k in {"state", "phase"}}
                )

        self.store.atomic(keys, update)

    def run(self, identifier):
        key, now = f"operation:{identifier}", time.time()

        def claim(rows):
            row = rows[key]
            if (
                not row
                or row["state"] in {"succeeded", "failed"}
                or row.get("lease", 0) > now
            ):
                return None
            row.update(state="running", lease=now + LEASE)
            return row

        row = self.store.atomic([key], claim)
        if not row:
            return
        try:
            if row["type"] == "export":
                self.export(row)
            else:
                self.erase(row)
        except Exception:
            # Provider messages can contain personal information. Keep errors generic.
            if row["type"] == "export":
                self.storage.delete_prefix(f"exports/{identifier}/")
                self.progress(
                    row,
                    state="failed",
                    phase="Download preparation failed; try again",
                    lease=0,
                    preferences=None,
                    expires=time.time() + DAY,
                )
            else:
                logging.error(
                    "Account cleanup requires retry",
                    extra={"event": "account_cleanup_retry"},
                )
                self.progress(
                    row,
                    state="queued",
                    phase="Cleanup will retry automatically",
                    lease=0,
                    retry_after=time.time() + 60,
                )

    def export(self, row):
        owner, identifier = row["owner"], row["id"]
        if not enabled(self.store, owner):
            raise Rejected("Account unavailable", 403)
        self.progress(row, phase="Collecting records and files")
        captured_at = time.time()
        records = self.store.owned(owner)
        records = [
            (key, value)
            for key, value in records
            if value["kind"] not in {"operation", "activity"}
        ]
        grouped = {}
        files = {}
        for _, record in records:
            grouped.setdefault(record["kind"], []).append(record)
            if record["kind"] == "build":
                prefix = f"builds/{record['id']}/"
            elif record["kind"] == "asset":
                prefix = f"assets/{record['id']}/"
            else:
                continue
            expected = [record["object"]] if record.get("object") else []
            expected += [
                a["object"] for a in record.get("artifacts", []) if a.get("object")
            ]
            for name in expected:
                if name.startswith(prefix):
                    files[name] = {"object": name, "missing": True}
            for item in self.storage.list_files(prefix):
                files[item["object"]] = item
        profile = self.verifier.profile(
            [r for _, r in records if r["kind"] == "identity"]
        )
        manifest = {
            "version": 1,
            "prepared_at": captured_at,
            "files": [],
            "unavailable": [],
            "boundary": "Records and retained files captured when preparation began. Active builds may change afterward.",
            "browser_preferences": "Current browser only; other devices are not included.",
        }
        with (
            writing(self.store, owner),
            self.storage.export_file(
                f"exports/{identifier}/account-data.zip", time.time() + DAY
            ) as output,
        ):
            with zipfile.ZipFile(
                output, "w", zipfile.ZIP_DEFLATED, allowZip64=True
            ) as archive:
                archive.writestr("records.json", json_bytes(grouped))
                archive.writestr("profile.json", json_bytes(profile))
                archive.writestr(
                    "browser-preferences.json", json_bytes(row["preferences"])
                )
                for name, item in files.items():
                    if item.get("missing"):
                        manifest["unavailable"].append(name)
                        continue
                    if not enabled(self.store, owner):
                        raise Rejected("Account unavailable", 403)
                    # Object paths are server-generated, but reject traversal defensively.
                    path = PurePosixPath(name)
                    if path.is_absolute() or ".." in path.parts or "\\" in name:
                        raise ValueError("Unsafe archive path")
                    with tempfile.TemporaryFile() as source:
                        try:
                            self.storage.copy_to(item, source)
                        except FileNotFoundError:
                            manifest["unavailable"].append(name)
                            continue
                        source.seek(0)
                        with archive.open(name, "w", force_zip64=True) as destination:
                            while chunk := source.read(1024 * 1024):
                                destination.write(chunk)
                    manifest["files"].append({"path": name, "size": item["size"]})
                archive.writestr("manifest.json", json_bytes(manifest))
            if not enabled(self.store, owner):
                raise Rejected("Account unavailable", 403)
        self.progress(
            row,
            state="succeeded",
            phase="Download ready",
            lease=0,
            preferences=None,
            expires=time.time() + DAY,
        )

    def erase(self, row):
        owner = row["owner"]
        self.progress(row, phase="Stopping builds and uploads")
        records = self.store.owned(owner)
        builds = [r for _, r in records if r["kind"] == "build"]
        for build in builds:
            key = f"build:{build['id']}"

            def cancel(rows):
                if rows[key]:
                    rows[key].update(cancel=True, deleted=True)

            self.store.atomic([key], cancel)
        # All object writers register activity before writing. Expired leases are safe
        # only after the enforced job timeout (or bounded API write) has passed.
        waiting = any(
            r["kind"] == "activity" and r["expires"] > time.time()
            for _, r in self.store.owned(owner)
        )
        for build in builds:
            if build.get("started") and build["state"] not in {
                "succeeded",
                "partial",
                "failed",
                "cancelled",
                "expired",
            }:
                waiting = not self.dispatcher.stop(build) or waiting
        # An exporting job may still hold a records snapshot in memory or a temp file.
        for _, operation in records:
            if operation["kind"] == "operation" and operation["type"] == "export":
                waiting = operation.get("lease", 0) > time.time() or waiting
        if waiting:
            self.progress(
                row,
                state="queued",
                phase="Waiting for active work to stop",
                lease=0,
                retry_after=time.time() + 60,
            )
            return
        self.progress(row, phase="Removing files and account records")
        for _, record in records:
            kind = record["kind"]
            if kind in {"build", "asset"}:
                prefix = "builds" if kind == "build" else "assets"
                self.storage.delete_prefix(f"{prefix}/{record['id']}/")
            elif kind == "operation" and record["type"] == "export":
                self.storage.delete_prefix(f"exports/{record['id']}/")
        identities = [r for _, r in records if r["kind"] == "identity"]
        for identity in identities:
            self.verifier.delete(identity["issuer"], identity["subject"])
        # Slot arrays are shared; erase only this account's references.
        ids = {b["id"] for b in builds}
        for group in ("full", "preview"):
            key = f"slots:{group}"

            def release(rows):
                if rows[key]:
                    rows[key]["ids"] = [i for i in rows[key]["ids"] if i not in ids]

            self.store.atomic([key], release)
        # Delete children first, preserving their object/identity locators on failure.
        account_key, operation_key = f"account:{owner}", f"operation:{row['id']}"
        for key, _ in self.store.owned(owner):
            if key not in {account_key, operation_key}:
                self.store.atomic([key], lambda rows, key=key: rows.update({key: None}))
        remaining = self.store.owned(owner)
        if any(key not in {account_key, operation_key} for key, _ in remaining):
            raise RuntimeError("Cleanup incomplete")
        receipt_key = f"receipt:{row['receipt']}"

        def finish(rows):
            rows[account_key] = rows[operation_key] = None
            rows[receipt_key] = {
                "kind": "receipt",
                "state": "succeeded",
                "phase": "Your account and data have been deleted",
                "expires": time.time() + DAY,
            }

        self.store.atomic([account_key, operation_key, receipt_key], finish)


def reconcile_operations(config, store, storage, verifier, dispatcher):
    now = time.time()
    for row in store.list("operation"):
        if row.get("expires", float("inf")) <= now:
            storage.delete_prefix(f"exports/{row['id']}/")
            key = f"operation:{row['id']}"
            store.atomic([key], lambda rows, key=key: rows.update({key: None}))
        elif (
            row["state"] in {"queued", "running"}
            and row.get("lease", 0) <= now
            and row.get("retry_after", 0) <= now
        ):
            # Persist an outbox dispatch deadline before launching. Reconciliation
            # retries ambiguous launches; the job claim prevents duplicate execution.
            key = f"operation:{row['id']}"

            def dispatch(rows):
                current = rows[key]
                if not current or current.get("dispatch_until", 0) > now:
                    return False
                current["dispatch_until"] = now + 120
                return True

            if store.atomic([key], dispatch):
                dispatcher.launch_operation(row["id"])
    # Migrate older auxiliary expirations and remove anonymous receipts explicitly;
    # TTL is a backstop, never the sole deletion mechanism.
    for key, value in store.retention_records():
        expires = value.get("expires", float("inf"))
        if (
            value["kind"] in {"quota", "idempotency"}
            and "expires" in value
            and not value.get("retention_version")
        ):
            # Old quotas lived 32 days; old idempotency records lived 31.
            reduction = (2 if value["kind"] == "quota" else 1) * DAY

            def migrate(rows):
                current = rows[key]
                if current and not current.get("retention_version"):
                    current.update(
                        expires=current["expires"] - reduction, retention_version=1
                    )

            store.atomic([key], migrate)
        elif expires <= now and value["kind"] in {"receipt", "activity"}:
            store.atomic([key], lambda rows, key=key: rows.update({key: None}))


def main():
    from .config import Config
    from .dispatch import Dispatcher
    from .identity import FirebaseVerifier
    from .storage import Storage
    from .store import FirestoreStore

    config = Config()
    store = FirestoreStore(config.project)
    DataOperations(
        store, Storage(config), FirebaseVerifier(), Dispatcher(config, store)
    ).run(os.environ["OPERATION_ID"])


if __name__ == "__main__":
    main()
