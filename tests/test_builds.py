import concurrent.futures
import unittest

from opensiddur_infra.builds import Builds, Rejected
from opensiddur_infra.identity import Accounts
from opensiddur_infra.store import MemoryStore


class Verifier:
    def verify(self, token):
        return {"iss": "https://example.test", "sub": token, "auth_time": 1000}


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.now = 1000000
        self.builds = Builds(self.store, "release", clock=lambda: self.now)
        self.accounts = Accounts(self.store, Verifier())
        self.owner = self.user("one")

    def user(self, token):
        owner = self.accounts.authenticate(token).account_id
        key = f"account:{owner}"
        self.store.atomic(
            [key], lambda values: values[key].update(consent={"version": "test"})
        )
        return owner

    def submit(self, owner=None, key="request", kind="full", settings=None):
        return self.builds.submit(
            owner or self.owner,
            settings or {"book": {"project": "synthetic"}},
            ["pdf"],
            kind,
            key,
        )

    def test_identity_is_stable_and_not_provider_subject(self):
        self.assertEqual(self.accounts.authenticate("one").account_id, self.owner)
        self.assertNotEqual(self.owner, "one")

    def test_idempotency_does_not_double_charge(self):
        first = self.submit()
        self.assertEqual(first["id"], self.submit()["id"])
        with self.assertRaises(Rejected) as error:
            self.submit(settings={"book": {"project": "other"}})
        self.assertEqual(error.exception.status, 409)

    def test_concurrent_admission_allows_only_one_outstanding_build(self):
        def attempt(i):
            try:
                return self.submit(key=str(i))["id"]
            except Rejected:
                return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(attempt, range(8)))
        self.assertEqual(sum(value is not None for value in outcomes), 1)

    def test_claim_is_idempotent_and_limits_running_workers(self):
        a, b, c = (
            self.submit(),
            self.submit(self.user("two")),
            self.submit(self.user("three")),
        )
        self.assertIsNotNone(self.builds.claim(a["id"], "execution-a"))
        self.assertIsNone(self.builds.claim(a["id"], "execution-duplicate"))
        self.builds.claim(b["id"], "execution-b")
        with self.assertRaises(Rejected):
            self.builds.claim(c["id"], "execution-c")

    def test_finish_refunds_runtime_and_preserves_partial_results(self):
        row = self.submit()
        self.builds.claim(row["id"], "run")
        self.now += 90
        self.builds.finish(
            row["id"],
            "partial",
            {"html": {"state": "succeeded"}},
            [{"name": "book.html"}],
        )
        done = self.builds.get(self.owner, row["id"])
        self.assertEqual(done["elapsed"], 90)
        self.assertEqual(done["state"], "partial")
        self.assertEqual(self.store.get(row["user_quota"])["seconds"], 90)
        next_build = self.submit(key="second")
        self.assertEqual(next_build["seconds"], 10800 - 90)

    def test_owner_check_and_revocable_sharing(self):
        row = self.submit()
        with self.assertRaises(Rejected):
            self.builds.get(self.user("intruder"), row["id"])
        self.builds.finish(row["id"], "succeeded")
        token = self.builds.share(self.owner, row["id"], True)
        self.assertEqual(self.builds.shared(token)["id"], row["id"])
        replacement = self.builds.share(self.owner, row["id"], True)
        with self.assertRaises(Rejected):
            self.builds.shared(token)
        self.builds.share(self.owner, row["id"], False)
        with self.assertRaises(Rejected):
            self.builds.shared(replacement)

    def test_expiry_is_enforced_before_physical_cleanup(self):
        row = self.submit()
        self.builds.finish(row["id"], "succeeded")
        self.now += 30 * 86400
        with self.assertRaises(Rejected) as error:
            self.builds.get(self.owner, row["id"])
        self.assertEqual(error.exception.status, 410)

    def test_cancel_and_finish_do_not_publish_artifacts(self):
        row = self.submit()
        self.builds.claim(row["id"], "run")
        self.builds.cancel(self.owner, row["id"])
        self.builds.finish(row["id"], "succeeded", artifacts=[{"name": "secret.pdf"}])
        done = self.builds.get(self.owner, row["id"])
        self.assertEqual(done["state"], "cancelled")
        self.assertEqual(done["artifacts"], [])

    def test_daily_build_count_is_not_refunded_after_admission(self):
        for i in range(5):
            row = self.submit(key=str(i))
            self.builds.cancel(self.owner, row["id"])
        with self.assertRaises(Rejected):
            self.submit(key="sixth")

    def test_clock_crossing_midnight_refunds_original_ledger(self):
        row = self.submit()
        self.builds.claim(row["id"], "run")
        self.now += 86400
        self.builds.finish(row["id"], "failed")
        self.assertEqual(self.store.get(row["user_quota"])["seconds"], 10800)
        self.assertIsNotNone(self.submit(key="next-day"))

    def test_without_consent_admission_is_rejected(self):
        key = f"account:{self.owner}"
        self.store.atomic([key], lambda values: values[key].update(consent=None))
        with self.assertRaises(Rejected) as error:
            self.submit()
        self.assertEqual(error.exception.status, 403)
