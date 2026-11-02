import time
import unittest
from dataclasses import replace

from opensiddur_infra.builds import Builds, Rejected
from opensiddur_infra.config import Config
from opensiddur_infra.identity import Accounts
from opensiddur_infra.maintenance import reconcile
from opensiddur_infra.store import MemoryStore


class Verifier:
    def verify(self, token):
        return {"iss": "https://example.test", "sub": token, "auth_time": 0}


class Storage:
    def __init__(self):
        self.deleted = []

    def delete_prefix(self, prefix):
        self.deleted.append(prefix)


class Dispatcher:
    def __init__(self):
        self.enqueued = []
        self.launched = []

    def enqueue(self, identifier):
        self.enqueued.append(identifier)

    def launch(self, row):
        self.launched.append(row["id"])


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.storage = Storage()
        self.dispatcher = Dispatcher()
        self.builds = Builds(self.store, "test")
        self.owner = Accounts(self.store, Verifier()).authenticate("owner").account_id
        key = f"account:{self.owner}"
        self.store.atomic(
            [key], lambda rows: rows[key].update(consent={"version": "test"})
        )

    def submit(self, key="one"):
        return self.builds.submit(self.owner, {}, ["html"], "html", key)

    def maintain(self):
        return reconcile(
            replace(Config(), release="test"),
            self.store,
            self.builds,
            self.storage,
            self.dispatcher,
        )

    def test_accepted_outbox_survives_missing_cloud_task(self):
        row = self.submit()
        self.maintain()
        self.assertIn(row["id"], self.dispatcher.enqueued)

    def test_ambiguous_dispatch_is_retried_without_mutating_build_identity(self):
        row = self.submit()
        self.builds.update(row["id"], dispatch=time.time() - 240)
        self.maintain()
        self.assertEqual(self.dispatcher.launched, [row["id"]])
        self.assertEqual(self.store.get("build:" + row["id"])["state"], "queued")

    def test_expired_history_and_objects_are_removed(self):
        row = self.submit()
        self.builds.finish(row["id"], "succeeded")
        key = "build:" + row["id"]
        self.store.atomic([key], lambda rows: rows[key].update(expires=time.time() - 1))
        self.maintain()
        self.assertIsNone(self.store.get(key))
        self.assertIn("builds/" + row["id"] + "/", self.storage.deleted)

    def test_running_deleted_build_is_not_ttl_eligible_in_memory_model(self):
        row = self.submit()
        self.builds.claim(row["id"], "preview")
        key = "build:" + row["id"]
        self.store.atomic(
            [key],
            lambda rows: rows[key].update(
                cancel=True, deleted=True, expires=time.time() - 1
            ),
        )
        self.builds.finish(row["id"], "succeeded", artifacts=[{"name": "private.html"}])
        stored = self.store.get(key)
        self.assertEqual(stored["state"], "cancelled")
        self.assertEqual(stored["artifacts"], [])
        with self.assertRaises(Rejected):
            self.builds.get(self.owner, row["id"])

    def test_unreferenced_logos_expire_but_saved_preset_logos_survive(self):
        for identifier in ("unused", "saved"):
            key = "asset:" + identifier
            self.store.atomic(
                [key],
                lambda rows, key=key, identifier=identifier: rows.update(
                    {
                        key: {
                            "kind": "asset",
                            "id": identifier,
                            "owner": self.owner,
                            "created": time.time() - 90000,
                        }
                    }
                ),
            )
        self.store.atomic(
            ["preset:one"],
            lambda rows: rows.update(
                {
                    "preset:one": {
                        "kind": "preset",
                        "owner": self.owner,
                        "asset": "saved",
                    }
                }
            ),
        )
        self.maintain()
        self.assertIsNone(self.store.get("asset:unused"))
        self.assertIsNotNone(self.store.get("asset:saved"))
