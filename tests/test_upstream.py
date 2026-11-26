"""Which upstream commits production and development are built from, without GitHub."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import release_id  # noqa: E402
import upstream  # noqa: E402

# In GitHub's order, by the date of each release's commit: v0.8.0 was cut from an older
# commit than v0.7.0 but published after it. Commits are the ref name, hex-encoded.
RELEASES = {
    "processor": [
        {
            "tag_name": "v0.10.0",
            "draft": True,
            "prerelease": False,
            "published_at": None,
        },
        {
            "tag_name": "v0.9.0-rc.1",
            "draft": False,
            "prerelease": True,
            "published_at": "2026-11-20T10:00:00Z",
        },
        {
            "tag_name": "v0.7.0",
            "draft": False,
            "prerelease": False,
            "published_at": "2026-11-08T22:15:30Z",
        },
        {
            "tag_name": "v0.8.0",
            "draft": False,
            "prerelease": False,
            "published_at": "2026-11-15T10:00:00Z",
        },
    ],
    "projects": [
        {
            "tag_name": "v20261108",
            "draft": False,
            "prerelease": False,
            "published_at": "2026-11-08T23:36:49Z",
        },
    ],
}


def sha(ref: str) -> str:
    return ref.encode().hex().ljust(40, "0")[:40]


def main_head(name: str) -> str:
    return sha(f"main-{name}")


def fake_gh(*args: str) -> str:
    path = args[1]
    name = path.split("/")[2].removeprefix("opensiddur-")
    if "/releases/tags/" in path:
        tag = path.rsplit("/", 1)[1]
        for release in RELEASES[name]:
            if release["tag_name"] == tag:
                return json.dumps(release)
        raise subprocess.CalledProcessError(1, ["gh", *args])
    if "/releases" in path:
        return json.dumps(RELEASES[name])
    ref = path.rsplit("/", 1)[1]
    return main_head(name) if ref == "main" else sha(ref)


def full_release_pins(processor_tag: str = "v0.8.0", **override) -> dict:
    pins = {
        "processor": sha(processor_tag),
        "projects": sha("v20261108"),
        "tags": {"processor": processor_tag, "projects": "v20261108"},
        "channel": "release",
    }
    return pins | override


class FakeGitHub(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(upstream, "gh", fake_gh)
        patcher.start()
        self.addCleanup(patcher.stop)


class TestResolve(FakeGitHub):
    def test_main_is_the_head_of_each_main_branch(self):
        pins = upstream.resolve("main")
        self.assertEqual(main_head("processor"), pins["processor"])
        self.assertEqual(main_head("projects"), pins["projects"])
        self.assertEqual("main", pins["channel"])
        self.assertNotIn("tags", pins)

    def test_release_is_the_newest_published_full_release(self):
        pins = upstream.resolve("release")
        self.assertEqual({"processor": "v0.8.0", "projects": "v20261108"}, pins["tags"])
        self.assertEqual(sha("v0.8.0"), pins["processor"])
        self.assertEqual("release", pins["channel"])

    def test_prereleases_are_never_taken(self):
        self.assertNotIn("v0.9.0-rc.1", upstream.resolve("release")["tags"].values())

    def test_drafts_are_never_taken(self):
        self.assertNotIn("v0.10.0", upstream.resolve("release")["tags"].values())

    def test_an_unknown_channel_is_refused(self):
        with self.assertRaises(SystemExit):
            upstream.resolve("prerelease")

    def test_a_repository_without_releases_is_refused(self):
        with mock.patch.dict(RELEASES, {"projects": []}), self.assertRaises(SystemExit):
            upstream.resolve("release")


class TestCheck(FakeGitHub):
    def test_an_older_full_release_is_accepted(self):
        self.assertEqual([], upstream.check(full_release_pins("v0.7.0")))

    def test_a_prerelease_is_refused(self):
        problems = upstream.check(full_release_pins("v0.9.0-rc.1"))
        self.assertEqual(1, len(problems))
        self.assertIn("opensiddur-processor", problems[0])
        self.assertIn("prerelease", problems[0])

    def test_a_tag_that_is_no_release_is_refused(self):
        problems = upstream.check(full_release_pins("some-branch"))
        self.assertIn("not a published release", problems[0])

    def test_a_commit_that_is_not_the_releases_is_refused(self):
        problems = upstream.check(full_release_pins(processor=sha("v0.7.0")))
        self.assertIn("not the commit", problems[0])

    def test_main_pins_are_refused(self):
        self.assertEqual(2, len(upstream.check(upstream.resolve("main"))))


class InADirectory(FakeGitHub):
    def setUp(self):
        super().setUp()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        previous = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)

    def given(self, pins: dict) -> str:
        path = self.root / "given.json"
        path.write_text(json.dumps(pins))
        return str(path)

    def chosen(self) -> dict:
        return json.loads((self.root / ".bundle/upstream.json").read_text())


class TestChoose(InADirectory):
    """Which pins each kind of deployment builds from."""

    def test_development_follows_main(self):
        upstream.choose("dev")
        self.assertEqual(main_head("processor"), self.chosen()["processor"])
        self.assertEqual("main", self.chosen()["channel"])

    def test_development_takes_the_pins_it_is_given(self):
        upstream.choose("dev", "", self.given(full_release_pins("v0.7.0")))
        self.assertEqual(sha("v0.7.0"), self.chosen()["processor"])

    def test_production_finds_the_newest_releases(self):
        upstream.choose("prod", "v1.2.3")
        self.assertEqual(sha("v0.8.0"), self.chosen()["processor"])

    def test_a_release_uses_the_releases_it_was_resolved_with(self):
        for environment in ("dev", "prod"):
            with self.subTest(environment=environment):
                given = self.given(full_release_pins("v0.7.0"))
                upstream.choose(environment, "v1.2.3", given)
                self.assertEqual(sha("v0.7.0"), self.chosen()["processor"])

    def test_a_release_refuses_pins_that_are_not_full_releases(self):
        for pins in (full_release_pins("v0.9.0-rc.1"), upstream.resolve("main")):
            for environment in ("dev", "prod"):
                with self.subTest(pins=pins, environment=environment):
                    with self.assertRaises(SystemExit):
                        upstream.choose(environment, "v1.2.3", self.given(pins))

    def test_a_pin_that_is_not_a_commit_hash_is_refused(self):
        given = self.given({"processor": "main", "projects": sha("v20261108")})
        with self.assertRaises(SystemExit):
            upstream.choose("dev", "", given)


class TestTheChosenPins(InADirectory):
    """The build reads the pins deploy.sh chose, and they are part of the release ID."""

    def setUp(self):
        super().setUp()
        for name in (
            "Dockerfile",
            "pyproject.toml",
            "uv.lock",
            "fonts.lock.json",
            "previews.lock.json",
            "web/package-lock.json",
        ):
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            (self.root / name).write_text(name)

    def test_without_a_choice_the_build_stops_and_says_what_to_run(self):
        with self.assertRaises(SystemExit) as raised:
            upstream.read_pins()
        self.assertIn("upstream.py choose", str(raised.exception))

    def test_the_chosen_pins_are_used(self):
        upstream.choose("dev")
        self.assertEqual(main_head("processor"), upstream.read_pins()["processor"])

    def test_different_pins_make_a_different_release(self):
        upstream.choose("dev")
        development = release_id.release_identity()
        upstream.choose("prod")
        production = release_id.release_identity()
        upstream.choose("dev", "", self.given(full_release_pins("v0.7.0")))
        self.assertEqual(
            3, len({development, production, release_id.release_identity()})
        )


if __name__ == "__main__":
    unittest.main()
