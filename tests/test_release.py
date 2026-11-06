"""Exercise release validation and source pinning without GitHub or Google Cloud."""

import os
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_release_notes_require_matching_version_and_include_pins(tmp_path, monkeypatch):
    for name in (
        "pyproject.toml",
        "uv.lock",
        "CHANGELOG.md",
        "releases.lock.json",
        "previews.lock.json",
        "fonts.lock.json",
        "web/package.json",
        "web/package-lock.json",
    ):
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    monkeypatch.chdir(tmp_path)
    version = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    notes = subprocess.check_output(
        ["python3", str(ROOT / "scripts/release_notes.py"), f"v{version}"], text=True
    )
    assert all(
        name in notes
        for name in ("processor", "projects", "font pack", "preview fixtures")
    )
    major, minor, patch = map(int, version.split("."))
    for invalid in ("v0.01.0", f"v{major}.{minor}.{patch + 1}", "main"):
        result = subprocess.run(
            ["python3", str(ROOT / "scripts/release_notes.py"), invalid], check=False
        )
        assert result.returncode != 0


@pytest.fixture
def source_repo(tmp_path, monkeypatch):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True).strip()

    git("init", "-q")
    git("config", "user.email", "builder@example.test")
    git("config", "user.name", "Builder Test")
    git("commit", "--allow-empty", "-qm", "release commit")
    tagged = git("rev-parse", "HEAD")
    git("tag", "-am", "v0.1.0", "v0.1.0")
    git("commit", "--allow-empty", "-qm", "main moved")
    current = git("rev-parse", "HEAD")
    gh = tmp_path / "gh"
    gh.write_text('#!/bin/sh\nprintf "%s\\n" "${TEST_RELEASE_IS_DRAFT:-false}"\n')
    gh.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("GITHUB_SHA", current)
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    def resolve(tag, mode):
        return subprocess.run(
            ["bash", str(ROOT / "scripts/resolve_release.sh"), tag, mode],
            cwd=tmp_path,
            check=False,
        )

    return resolve, tagged, output


def test_retry_resolves_published_tag_even_when_main_advances(source_repo):
    resolve, tagged, output = source_repo
    assert resolve("v0.1.0", "retry-production").returncode == 0
    assert output.read_text() == f"commit={tagged}\n"


def test_conflicting_tag_and_draft_retry_are_rejected(source_repo, monkeypatch):
    resolve, _, output = source_repo
    assert resolve("v0.1.0", "release").returncode != 0
    monkeypatch.setenv("TEST_RELEASE_IS_DRAFT", "true")
    assert resolve("v0.1.0", "retry-production").returncode != 0
    assert not output.exists()
