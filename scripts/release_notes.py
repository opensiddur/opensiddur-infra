"""Validate a Builder version and generate the notes for its annotated tag.

    release_notes.py vX.Y.Z [PINS]

PINS is the upstream pins file the release was resolved with (``upstream.py resolve
release``); without it the notes list only the inputs pinned in this repository.
"""

import json
import re
import sys
import tomllib
from pathlib import Path


def notes(tag, upstream=None):
    if not re.fullmatch(r"v(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){2}", tag):
        raise ValueError("Use a version tag in vX.Y.Z format.")
    version = tag[1:]
    python_version = tomllib.loads(Path("pyproject.toml").read_text())["project"][
        "version"
    ]
    packages = tomllib.loads(Path("uv.lock").read_text())["package"]
    locked_python = next(
        p["version"] for p in packages if p["name"] == "opensiddur-infra"
    )
    web = json.loads(Path("web/package.json").read_text())
    lock = json.loads(Path("web/package-lock.json").read_text())
    if {
        python_version,
        locked_python,
        web["version"],
        lock["version"],
        lock["packages"][""]["version"],
    } != {version}:
        raise ValueError(
            "The requested version must match both packages and lockfiles."
        )
    changelog = Path("CHANGELOG.md").read_text()
    match = re.search(
        rf"^## \[{re.escape(version)}\](?: - \d{{4}}-\d{{2}}-\d{{2}})?\n(.*?)(?=^## |\Z)",
        changelog,
        re.MULTILINE | re.DOTALL,
    )
    if not match or not match[1].strip():
        raise ValueError(f"Add a nonempty [{version}] entry to CHANGELOG.md.")
    revisions = json.loads(Path(upstream).read_text()) if upstream else {}
    revisions["preview fixtures"] = json.loads(Path("previews.lock.json").read_text())[
        "revision"
    ]
    revisions["font pack"] = json.loads(Path("fonts.lock.json").read_text())["revision"]
    tags = revisions.get("tags") or {}
    pins = "\n".join(
        f"- {name}: "
        + (f"{tags[name]} " if name in tags else "")
        + f"`{revisions[name]}`"
        for name in ("processor", "projects", "preview fixtures", "font pack")
        if name in revisions
    )
    return f"{match[1].strip()}\n\n## Pinned inputs\n\n{pins}"


if __name__ == "__main__":
    try:
        print(notes(*sys.argv[1:3]))
    except ValueError as error:
        sys.exit(str(error))
