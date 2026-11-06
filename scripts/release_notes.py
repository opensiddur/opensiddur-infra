"""Validate a Builder version and generate the notes for its annotated tag."""

import json
import re
import sys
import tomllib
from pathlib import Path


def notes(tag):
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
    revisions = json.loads(Path("releases.lock.json").read_text())
    revisions["preview fixtures"] = json.loads(Path("previews.lock.json").read_text())[
        "revision"
    ]
    revisions["font pack"] = json.loads(Path("fonts.lock.json").read_text())["revision"]
    pins = "\n".join(
        f"- {name}: `{revisions[name]}`"
        for name in ("processor", "projects", "preview fixtures", "font pack")
    )
    return f"{match[1].strip()}\n\n## Pinned inputs\n\n{pins}"


if __name__ == "__main__":
    try:
        print(notes(sys.argv[1]))
    except ValueError as error:
        sys.exit(str(error))
