"""Opt-in two-account probe against development Firestore, Storage and Firebase.

Executes the new service locally with production adapters; Cloud Run dispatch/UI
must additionally be smoke-tested after deploying the new runtime image.
"""

import argparse
import hashlib
import io
import json
import secrets
import subprocess
import time
import uuid
import zipfile
from dataclasses import replace

import firebase_admin
from firebase_admin import auth
from firebase_admin import credentials as firebase_credentials
from google.oauth2.credentials import Credentials

from opensiddur_infra.config import Config
from opensiddur_infra.data_operations import DataOperations, digest
from opensiddur_infra.identity import FirebaseVerifier, Principal
from opensiddur_infra.storage import Storage
from opensiddur_infra.store import FirestoreStore


class ProbeCredential(firebase_credentials.Base):
    def __init__(self, credential):
        self.credential = credential

    def get_credential(self):
        return self.credential


class NoRunningBuilds:
    def stop(self, row):
        raise AssertionError("The synthetic probe must not launch compiler jobs")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, choices=["opensiddur-builder-dev"])
    args = parser.parse_args()
    token = subprocess.check_output(
        ["gcloud", "auth", "print-access-token"], text=True, timeout=30
    ).strip()
    credential = Credentials(token, quota_project_id=args.project)
    firebase_admin.initialize_app(
        ProbeCredential(credential), {"projectId": args.project}
    )
    config = replace(Config(), project=args.project, bucket=args.project + "-artifacts")
    store, storage = (
        FirestoreStore(args.project, credentials=credential),
        Storage(config, credentials=credential),
    )
    verifier = FirebaseVerifier()
    operations = DataOperations(store, storage, verifier, NoRunningBuilds())
    accounts = []
    receipts = []
    try:
        for _ in range(2):
            owner, uid = str(uuid.uuid4()), "account-data-probe-" + uuid.uuid4().hex
            auth.create_user(
                uid=uid,
                email_verified=True,
                display_name="Synthetic data-erasure probe",
            )
            principal = Principal(
                owner,
                "https://securetoken.google.com/" + args.project,
                uid,
                int(time.time()),
            )
            accounts.append(principal)
            identity = hashlib.sha256(f"{principal.issuer}\0{uid}".encode()).hexdigest()
            asset = str(uuid.uuid4())
            entries = {
                f"account:{owner}": {
                    "kind": "account",
                    "id": owner,
                    "owner": owner,
                    "enabled": True,
                    "consent": None,
                },
                f"identity:{identity}": {
                    "kind": "identity",
                    "id": identity,
                    "owner": owner,
                    "issuer": principal.issuer,
                    "subject": uid,
                },
                f"asset:{asset}": {
                    "kind": "asset",
                    "id": asset,
                    "owner": owner,
                    "object": f"assets/{asset}/logo.png",
                    "created": time.time(),
                },
            }
            store.atomic(
                list(entries), lambda rows, entries=entries: rows.update(entries)
            )
            storage.put(
                f"assets/{asset}/logo.png", b"synthetic-private-logo", "image/png"
            )
        first, second = accounts
        identifier = operations.start_export(first.account_id, {"advanced": True})["id"]
        operations.run(identifier)
        assert operations.status(first.account_id, identifier)["state"] == "succeeded"
        with zipfile.ZipFile(
            io.BytesIO(storage.read(f"exports/{identifier}/account-data.zip"))
        ) as archive:
            records = json.loads(archive.read("records.json"))
            assert records["account"][0]["id"] == first.account_id
            assert second.account_id not in archive.read("records.json").decode()
            assert json.loads(archive.read("browser-preferences.json"))["advanced"]
            assert any(n.startswith("assets/") for n in archive.namelist())
        receipt = secrets.token_urlsafe(32)
        receipts.append(receipt)
        operations.start_delete(first, receipt)
        deletion = store.get(f"account:{first.account_id}")["deletion"]
        operations.run(deletion)
        assert not store.owned(first.account_id)
        assert operations.receipt(receipt)["state"] == "succeeded"
        assert not storage.list_files(f"exports/{identifier}/")
        try:
            auth.get_user(first.subject)
        except auth.UserNotFoundError:
            pass
        else:
            raise AssertionError("Synthetic Firebase identity survived deletion")
        assert store.owned(second.account_id)
        auth.get_user(second.subject)
        for row in store.list("asset", second.account_id):
            assert storage.read(row["object"]) == b"synthetic-private-logo"
        print("Development export/erasure and second-account isolation passed")
    finally:
        # Cleanup only principals created by this probe, including failed operations.
        for principal in accounts:
            if store.get(f"account:{principal.account_id}"):
                receipt = secrets.token_urlsafe(32)
                account = store.get(f"account:{principal.account_id}")
                if account.get("deletion"):
                    operations.run(account["deletion"])
                else:
                    receipts.append(receipt)
                    operations.start_delete(principal, receipt)
                    operations.run(
                        store.get(f"account:{principal.account_id}")["deletion"]
                    )
                assert not store.owned(principal.account_id), (
                    "Synthetic cleanup incomplete"
                )
            verifier.delete(principal.issuer, principal.subject)
        for receipt in receipts:
            key = "receipt:" + digest(receipt)
            store.atomic([key], lambda rows, key=key: rows.update({key: None}))
        print("Synthetic accounts, files and receipts removed")


if __name__ == "__main__":
    main()
