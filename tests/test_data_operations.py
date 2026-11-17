import io
import json
import time
import unittest
import zipfile
from dataclasses import replace
from contextlib import contextmanager
from unittest.mock import patch

from fastapi.testclient import TestClient

from opensiddur_infra.api import create_app
from opensiddur_infra.config import Config
from opensiddur_infra.data_operations import (
    AccountStorage,
    DataOperations,
    digest,
    reconcile_operations,
    writing,
)
from opensiddur_infra.builds import Builds, Rejected
from opensiddur_infra.identity import Accounts
from opensiddur_infra.store import MemoryStore


class Verifier:
    def __init__(self):
        self.deleted = set()
        self.fail_delete = False
        self.age = 0

    def verify(self, token):
        if token in self.deleted:
            raise ValueError("User removed")
        return {"iss": "test", "sub": token, "auth_time": time.time() - self.age}

    def delete(self, issuer, subject):
        if self.fail_delete:
            raise RuntimeError("Temporary failure")
        self.deleted.add(subject)

    def profile(self, identities):
        return [
            {"uid": i["subject"], "email": "reader@example.test"} for i in identities
        ]


class Objects:
    def __init__(self):
        self.data = {}
        self.missing = set()
        self.broken = False

    def put(self, name, data, content_type, **kwargs):
        self.data[name] = data
        return {"object": name}

    @contextmanager
    def export_file(self, name, expires):
        with io.BytesIO() as output:
            yield output
            self.data[name] = output.getvalue()

    def list_files(self, prefix):
        return [
            {"object": k, "size": len(v), "generation": 1}
            for k, v in self.data.items()
            if k.startswith(prefix)
        ]

    def copy_to(self, item, destination):
        if item["object"] in self.missing:
            raise FileNotFoundError()
        if self.broken:
            raise RuntimeError("Storage failure")
        destination.write(self.data[item["object"]])

    def delete_prefix(self, prefix):
        self.data = {k: v for k, v in self.data.items() if not k.startswith(prefix)}

    def url(self, *args):
        return "https://storage.example.test/file"


class Dispatcher:
    def __init__(self):
        self.launched = []
        self.stopped = True

    def launch_operation(self, identifier):
        self.launched.append(identifier)

    def stop(self, row):
        return self.stopped


class DataTests(unittest.TestCase):
    def setUp(self):
        self.store, self.objects, self.verifier = MemoryStore(), Objects(), Verifier()
        self.dispatcher = Dispatcher()
        self.accounts = Accounts(self.store, self.verifier)
        self.principal = self.accounts.authenticate("reader")
        self.owner = self.principal.account_id
        self.other = self.accounts.authenticate("other").account_id
        self.ops = DataOperations(
            self.store, self.objects, self.verifier, self.dispatcher
        )
        self.receipt = "a" * 64
        self.add(
            "preset:one",
            "preset",
            settings={"title": "שָׁלוֹם"},
            preferences={"advanced": True},
        )
        self.add("asset:logo", "asset", id="logo")
        self.add(
            "build:book",
            "build",
            id="book",
            state="succeeded",
            group="full",
            expires=time.time() - 1,
        )
        self.add("share:hash", "share", build="book")
        self.add("quota:user", "quota", key="quota:user", expires=time.time() + 10)
        self.add("idem:one", "idempotency", key="idem:one", expires=time.time() + 10)
        self.objects.data = {
            "builds/book/private.log": b"private log",
            "assets/logo/logo.png": b"\x89PNG\x00",
            "builds/other/book.pdf": b"other",
        }

    def add(self, record_key, kind, **fields):
        self.store.data[record_key] = {"kind": kind, "owner": self.owner, **fields}

    def start_export(self):
        return self.ops.start_export(self.owner, {"advanced": True})["id"]

    def test_zip_contains_all_owned_records_profile_preferences_and_files(self):
        identifier = self.start_export()
        self.assertEqual(self.start_export(), identifier)
        self.ops.run(identifier)
        row = self.ops.status(self.owner, identifier)
        self.assertEqual(row["state"], "succeeded")
        with zipfile.ZipFile(
            io.BytesIO(self.objects.data[f"exports/{identifier}/account-data.zip"])
        ) as archive:
            records = json.loads(archive.read("records.json"))
            self.assertEqual(
                set(records),
                {
                    "account",
                    "identity",
                    "preset",
                    "build",
                    "asset",
                    "quota",
                    "idempotency",
                    "share",
                },
            )
            self.assertEqual(records["preset"][0]["settings"]["title"], "שָׁלוֹם")
            self.assertEqual(archive.read("assets/logo/logo.png"), b"\x89PNG\x00")
            self.assertEqual(archive.read("builds/book/private.log"), b"private log")
            self.assertTrue(
                json.loads(archive.read("browser-preferences.json"))["advanced"]
            )
            self.assertNotIn("builds/other/book.pdf", archive.namelist())
            self.assertEqual(
                json.loads(archive.read("profile.json"))[0]["uid"], "reader"
            )
        with self.assertRaises(Rejected):
            self.ops.status(self.other, identifier)

    def test_missing_file_is_documented_but_storage_error_fails_export(self):
        self.objects.missing.add("builds/book/private.log")
        identifier = self.start_export()
        self.ops.run(identifier)
        with zipfile.ZipFile(
            io.BytesIO(self.objects.data[f"exports/{identifier}/account-data.zip"])
        ) as archive:
            self.assertEqual(
                json.loads(archive.read("manifest.json"))["unavailable"],
                ["builds/book/private.log"],
            )
            self.assertNotIn("builds/book/private.log", archive.namelist())
        self.objects.broken = True
        identifier = self.start_export()
        self.ops.run(identifier)
        self.assertEqual(self.ops.status(self.owner, identifier)["state"], "failed")
        self.assertNotIn(f"exports/{identifier}/account-data.zip", self.objects.data)

    def erase(self):
        self.ops.start_delete(self.principal, self.receipt)
        return self.store.get(f"account:{self.owner}")["deletion"]

    def test_erasure_removes_expired_records_files_auth_and_only_owned_slots(self):
        identifier = self.erase()
        self.ops.start_delete(self.principal, self.receipt)
        self.store.data["slots:full"] = {"kind": "slots", "ids": ["book", "other"]}
        self.store.data["quota:global"] = {"kind": "quota", "seconds": 20}
        with self.assertRaises(ValueError):
            self.accounts.authenticate("reader")
        self.ops.run(identifier)
        self.assertEqual(self.store.owned(self.owner), [])
        self.assertIn("reader", self.verifier.deleted)
        self.assertTrue(self.store.owned(self.other))
        self.assertEqual(self.objects.data, {"builds/other/book.pdf": b"other"})
        self.assertEqual(self.store.get("slots:full")["ids"], ["other"])
        self.assertEqual(self.store.get("quota:global")["seconds"], 20)
        self.assertEqual(self.ops.receipt(self.receipt)["state"], "succeeded")
        receipt = self.store.get("receipt:" + digest(self.receipt))
        self.assertNotIn("owner", receipt)
        self.assertNotIn(self.receipt, str(self.store.data))
        self.ops.run(identifier)  # Duplicate job is harmless.
        with self.assertRaises(ValueError):
            self.accounts.authenticate("reader")

    def test_provider_failure_retries_and_keeps_locators(self):
        identifier = self.erase()
        self.verifier.fail_delete = True
        self.ops.run(identifier)
        self.assertNotEqual(self.ops.receipt(self.receipt)["state"], "succeeded")
        self.assertTrue(self.store.list("identity", self.owner))
        self.verifier.fail_delete = False
        self.ops.run(identifier)
        self.assertEqual(self.store.owned(self.owner), [])

    def test_active_upload_defers_cleanup_and_fences_new_writes(self):
        with writing(self.store, self.owner):
            identifier = self.erase()
            self.ops.run(identifier)
            self.assertIn("Waiting", self.ops.receipt(self.receipt)["phase"])
            with self.assertRaises(Rejected):
                AccountStorage(self.objects, self.store, self.owner).put(
                    "assets/late/logo.png", b"late", "image/png"
                )
        self.ops.run(identifier)
        self.assertEqual(self.store.owned(self.owner), [])

    def test_running_worker_and_export_lease_defer_erasure(self):
        self.store.data["build:book"].update(started=time.time(), state="running")
        self.dispatcher.stopped = False
        export = self.start_export()
        self.store.data["operation:" + export].update(
            state="running", lease=time.time() + 100
        )
        identifier = self.erase()
        self.ops.run(identifier)
        self.assertTrue(self.store.list("build", self.owner)[0]["cancel"])
        self.dispatcher.stopped = True
        self.store.data["operation:" + export]["lease"] = 0
        self.ops.run(identifier)
        self.assertEqual(self.store.owned(self.owner), [])

    def test_late_claim_and_completion_do_not_publish_or_recreate(self):
        account = self.store.data[f"account:{self.owner}"]
        account["consent"] = {"version": "test"}
        builds = Builds(self.store, "test")
        row = builds.submit(self.owner, {}, ["html"], "html", "test")
        identifier = self.erase()
        self.assertIsNone(builds.claim(row["id"], "late"))
        self.ops.run(identifier)
        builds.update(row["id"], artifacts=[{"name": "late"}])
        builds.finish(row["id"], "succeeded", artifacts=[{"name": "late"}])
        self.assertEqual(self.store.owned(self.owner), [])

    def test_reconcile_dispatches_once_and_expires_export_and_receipt(self):
        identifier = self.start_export()
        for _ in range(2):
            reconcile_operations(
                Config(), self.store, self.objects, self.verifier, self.dispatcher
            )
        self.assertEqual(self.dispatcher.launched, [identifier])
        self.ops.run(identifier)
        with patch(
            "opensiddur_infra.data_operations.time.time",
            return_value=time.time() + 86401,
        ):
            with self.assertRaises(Rejected):
                self.ops.status(self.owner, identifier)
            reconcile_operations(
                Config(), self.store, self.objects, self.verifier, self.dispatcher
            )
        self.assertNotIn(f"exports/{identifier}/account-data.zip", self.objects.data)

    def test_deletion_during_object_put_removes_late_object(self):
        original = self.objects.put

        def interrupted(*args, **kwargs):
            result = original(*args, **kwargs)
            identifier = self.erase()
            self.ops.run(identifier)
            return result

        self.objects.put = interrupted
        with self.assertRaises(Rejected):
            AccountStorage(self.objects, self.store, self.owner).put(
                "assets/logo/late.png", b"private", "image/png"
            )
        self.assertNotIn("assets/logo/late.png", self.objects.data)

    def test_retention_migration_is_relative_to_original_expiry_and_runs_once(self):
        now = time.time()
        self.store.data["quota:user"].update(expires=now + 32 * 86400)
        self.store.data["idem:one"].update(expires=now + 31 * 86400)
        for _ in range(2):
            reconcile_operations(
                Config(), self.store, self.objects, self.verifier, self.dispatcher
            )
        for key in ("quota:user", "idem:one"):
            self.assertAlmostEqual(self.store.get(key)["expires"], now + 30 * 86400)

    def test_expired_completion_receipt_is_physically_removed(self):
        identifier = self.erase()
        self.ops.run(identifier)
        with patch(
            "opensiddur_infra.data_operations.time.time",
            return_value=time.time() + 86401,
        ):
            with self.assertRaises(Rejected):
                self.ops.receipt(self.receipt)
            reconcile_operations(
                Config(), self.store, self.objects, self.verifier, self.dispatcher
            )
        self.assertIsNone(self.store.get("receipt:" + digest(self.receipt)))

    def test_missing_expected_file_is_reported_even_if_gone_before_listing(self):
        self.store.data["asset:logo"]["object"] = "assets/logo/logo.png"
        self.objects.data.pop("assets/logo/logo.png")
        identifier = self.start_export()
        self.ops.run(identifier)
        with zipfile.ZipFile(
            io.BytesIO(self.objects.data[f"exports/{identifier}/account-data.zip"])
        ) as archive:
            self.assertIn(
                "assets/logo/logo.png",
                json.loads(archive.read("manifest.json"))["unavailable"],
            )

    def test_account_deletion_revokes_share_access_immediately(self):
        self.store.data[f"account:{self.owner}"]["consent"] = {"version": "test"}
        builds = Builds(self.store, "test")
        row = builds.submit(self.owner, {}, ["html"], "full", "shared")
        builds.finish(row["id"], "succeeded")
        token = builds.share(self.owner, row["id"], True)
        self.erase()
        with self.assertRaises(Rejected):
            builds.shared(token)


class DataApiTests(unittest.TestCase):
    def setUp(self):
        self.store, self.objects, self.verifier = MemoryStore(), Objects(), Verifier()
        self.dispatcher = Dispatcher()
        self.owner = (
            Accounts(self.store, self.verifier).authenticate("reader").account_id
        )
        self.client = TestClient(
            create_app(
                config=replace(Config(), app_check=False),
                store=self.store,
                verifier=self.verifier,
                storage=self.objects,
                dispatcher=self.dispatcher,
            )
        )
        self.headers = {"Authorization": "Bearer reader"}

    def test_export_auth_and_readiness(self):
        self.assertEqual(
            self.client.post("/api/v1/account/export", json={}).status_code, 401
        )
        response = self.client.post(
            "/api/v1/account/export",
            json={"browser_preferences": {"advanced": True}},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 202)
        identifier = response.json()["id"]
        self.assertEqual(
            self.client.get(
                f"/api/v1/account/exports/{identifier}/download", headers=self.headers
            ).status_code,
            409,
        )
        self.assertEqual(
            self.client.get(
                f"/api/v1/account/exports/{identifier}",
                headers={"Authorization": "Bearer other"},
            ).status_code,
            404,
        )

    def test_confirmation_recent_auth_and_receipt_isolation(self):
        body = {"confirmation": "delete", "receipt": "a" * 64}
        self.assertEqual(
            self.client.request(
                "DELETE", "/api/v1/account", json=body, headers=self.headers
            ).status_code,
            422,
        )
        body["confirmation"] = "DELETE"
        self.verifier.age = 301
        self.assertEqual(
            self.client.request(
                "DELETE", "/api/v1/account", json=body, headers=self.headers
            ).status_code,
            401,
        )
        self.assertTrue(self.store.get(f"account:{self.owner}")["enabled"])
        self.verifier.age = 0
        self.assertEqual(
            self.client.request(
                "DELETE", "/api/v1/account", json=body, headers=self.headers
            ).status_code,
            202,
        )
        self.assertEqual(
            self.client.get("/api/v1/account", headers=self.headers).status_code, 401
        )
        self.assertEqual(
            self.client.get(
                "/api/v1/account/deletion", headers=self.headers
            ).status_code,
            401,
        )
        self.assertEqual(
            self.client.get(
                "/api/v1/account/deletion",
                headers={"Authorization": "Deletion " + "b" * 64},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                "/api/v1/account/deletion",
                headers={"Authorization": "Deletion " + "a" * 64},
            ).status_code,
            200,
        )
