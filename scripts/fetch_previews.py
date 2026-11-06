"""Fetch only the immutable synthetic preview files, preserving the corpus pin."""

import json
import sys
import urllib.request
from pathlib import Path


def fetch_previews(processor):
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


if __name__ == "__main__":
    fetch_previews(Path(sys.argv[1]))
