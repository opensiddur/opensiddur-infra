#!/usr/bin/env python3
"""Fetch immutable upstream commits; never fetch raw source corpora/importer data."""

import json
import subprocess
import sys
from pathlib import Path

lock = json.loads(Path("releases.lock.json").read_text())
processor = Path(sys.argv[1])
for name, target in (
    ("processor", processor),
    ("projects", processor / "opensiddur-projects"),
):
    commit = lock[name]
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise SystemExit("Upstream references must be full commit hashes")
    target.mkdir(parents=True, exist_ok=True)
    if not (target / ".git").exists():
        subprocess.run(["git", "init", str(target)], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(target),
                "remote",
                "add",
                "origin",
                f"https://github.com/opensiddur/opensiddur-{name}.git",
            ],
            check=True,
        )
    subprocess.run(
        ["git", "-C", str(target), "fetch", "--depth=1", "origin", commit], check=True
    )
    subprocess.run(
        ["git", "-C", str(target), "checkout", "--detach", "FETCH_HEAD"], check=True
    )

# Overlay only the explicitly reviewed synthetic fixtures. Do not update the corpus
# or compiler merely to add previews; each has its own immutable release boundary.
import urllib.request

previews = json.loads(Path("previews.lock.json").read_text())
revision = previews["revision"]
if len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
    raise SystemExit("Preview references must be full commit hashes")
for language in ("he", "en"):
    for relative in (
        f"project/preview-{language}/index.xml",
        f"project/preview-{language}/parallel.xml",
        f"settings/preview-{language}/preview.yaml",
    ):
        url = f"https://raw.githubusercontent.com/opensiddur/opensiddur-projects/{revision}/{relative}"
        target = processor / "opensiddur-projects" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=60) as response:
            target.write_bytes(response.read())
