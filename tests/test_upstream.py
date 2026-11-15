"""Which upstream commits production and development are built from, without GitHub."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import release_id  # noqa: E402
import upstream  # noqa: E402

# Newest first, as GitHub lists them. Commits are the tag name padded to 40 characters.
RELEASES = {
    "processor": [
        {"tag_name": "v0.9.0", "draft": True, "prerelease": False},
        {"tag_name": "v0.8.0-rc.1", "draft": False, "prerelease": True},
        {"tag_name": "v0.7.0", "draft": False, "prerelease": False},
        {"tag_name": "v0.6.0", "draft": False, "prerelease": False},
    ],
    "projects": [
        {"tag_name": "v20261108", "draft": False, "prerelease": False},
    ],
}


def sha(tag: str) -> str:
    return tag.encode().hex().ljust(40, "0")[:40]


def fake_gh(*args: str) -> str:
    path = args[1]
    name = path.split("/")[2].removeprefix("opensiddur-")
    if "/releases" in path:
        return json.dumps(RELEASES[name])
    return sha(path.rsplit("/", 1)[1])


class TestResolve(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(upstream, "gh", fake_gh)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_development_takes_the_newest_prerelease(self):
        pins = upstream.resolve("prerelease")
        self.assertEqual({"processor": "v0.8.0-rc.1", "projects": "v20261108"}, pins["tags"])
        self.assertEqual(sha("v0.8.0-rc.1"), pins["processor"])
        self.assertEqual("prerelease", pins["channel"])

    def test_the_release_channel_skips_prereleases(self):
        self.assertEqual("v0.7.0", upstream.resolve("release")["tags"]["processor"])

    def test_drafts_are_never_taken(self):
        self.assertNotIn("v0.9.0", upstream.resolve("prerelease")["tags"].values())

    def test_an_unknown_channel_is_refused(self):
        with self.assertRaises(SystemExit):
            upstream.resolve("main")

    def test_a_repository_without_releases_is_refused(self):
        with mock.patch.dict(RELEASES, {"projects": []}), self.assertRaises(SystemExit):
            upstream.resolve("prerelease")


class TestCheck(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(upstream, "gh", fake_gh)
        patcher.start()
        self.addCleanup(patcher.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.lock = Path(directory.name) / "releases.lock.json"

    def _check(self, processor_tag: str) -> list[str]:
        self.lock.write_text(json.dumps(
            {"processor": sha(processor_tag), "projects": sha("v20261108")}))
        return upstream.check(self.lock)

    def test_an_older_full_release_is_accepted(self):
        self.assertEqual([], self._check("v0.6.0"))

    def test_a_prerelease_is_refused(self):
        problems = self._check("v0.8.0-rc.1")
        self.assertEqual(1, len(problems))
        self.assertIn("opensiddur-processor", problems[0])

    def test_a_commit_that_is_no_release_is_refused(self):
        self.assertEqual(1, len(self._check("some-branch-head")))

    def test_a_missing_pin_is_refused(self):
        self.lock.write_text(json.dumps({"processor": sha("v0.7.0")}))
        self.assertIn("(missing)", upstream.check(self.lock)[0])


class TestChoose(unittest.TestCase):
    """Which pins each kind of deployment builds from."""

    def setUp(self):
        patcher = mock.patch.object(upstream, "gh", fake_gh)
        patcher.start()
        self.addCleanup(patcher.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        previous = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)
        self._lock("v0.7.0")

    def _lock(self, processor_tag: str):
        (self.root / "releases.lock.json").write_text(json.dumps(
            {"processor": sha(processor_tag), "projects": sha("v20261108"),
             "channel": "release"}))

    def _chosen(self) -> dict:
        return json.loads((self.root / ".bundle/upstream.json").read_text())

    def test_development_follows_the_newest_prerelease(self):
        upstream.choose("dev")
        self.assertEqual(sha("v0.8.0-rc.1"), self._chosen()["processor"])

    def test_a_release_deployed_to_development_uses_production_pins(self):
        upstream.choose("dev", "v1.2.3")
        self.assertEqual(sha("v0.7.0"), self._chosen()["processor"])

    def test_production_uses_its_pins(self):
        upstream.choose("prod", "v1.2.3")
        self.assertEqual(sha("v0.7.0"), self._chosen()["processor"])

    def test_production_refuses_a_prerelease_pin(self):
        self._lock("v0.8.0-rc.1")
        for environment, version in (("prod", "v1.2.3"), ("dev", "v1.2.3")):
            with self.subTest(environment=environment), self.assertRaises(SystemExit):
                upstream.choose(environment, version)

    def test_development_takes_the_pins_it_is_given(self):
        given = self.root / "given.json"
        given.write_text(json.dumps({"processor": sha("v0.6.0"), "projects": sha("v20261108")}))
        upstream.choose("dev", "", str(given))
        self.assertEqual(sha("v0.6.0"), self._chosen()["processor"])

    def test_a_pin_that_is_not_a_commit_hash_is_refused(self):
        given = self.root / "given.json"
        given.write_text(json.dumps({"processor": "main", "projects": sha("v20261108")}))
        with self.assertRaises(SystemExit):
            upstream.choose("dev", "", str(given))


class TestTheChosenPins(unittest.TestCase):
    """The build reads the pins deploy.sh chose, and they are part of the release ID."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        previous = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)
        for name in ("Dockerfile", "pyproject.toml", "uv.lock", "fonts.lock.json",
                     "previews.lock.json", "web/package-lock.json"):
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            (self.root / name).write_text(name)
        (self.root / "releases.lock.json").write_text(
            json.dumps({"processor": sha("v0.7.0"), "projects": sha("v20261108")}))

    def _choose(self, processor_tag: str):
        (self.root / ".bundle").mkdir(exist_ok=True)
        (self.root / ".bundle/upstream.json").write_text(json.dumps(
            {"processor": sha(processor_tag), "projects": sha("v20261108"),
             "channel": "prerelease"}))

    def test_without_a_choice_the_build_uses_production_pins(self):
        self.assertEqual(sha("v0.7.0"), upstream.read_pins()["processor"])

    def test_the_chosen_pins_are_used(self):
        self._choose("v0.8.0-rc.1")
        self.assertEqual(sha("v0.8.0-rc.1"), upstream.read_pins()["processor"])

    def test_different_pins_make_a_different_release(self):
        production = release_id.release_identity()
        self._choose("v0.8.0-rc.1")
        development = release_id.release_identity()
        self._choose("v0.8.0-rc.2")
        self.assertEqual(3, len({production, development, release_id.release_identity()}))


if __name__ == "__main__":
    unittest.main()
