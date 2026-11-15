#!/usr/bin/env python3
"""The opensiddur-processor and opensiddur-projects commits a runtime is built from.

Production is built from ``releases.lock.json``, which pins published releases only;
``check`` refuses anything else. Development follows the newest release *or prerelease*
of each repository: ``resolve prerelease`` finds those commits each time development is
deployed, so a prerelease can be tried there without touching production's pins.

``deploy.sh`` writes the pins it chose (``choose``) to ``.bundle/upstream.json``; the image build
(``fetch_sources.py``, ``bundle.py``) and the release ID read that file when it exists,
and ``releases.lock.json`` otherwise.

    upstream.py choose ENVIRONMENT [VERSION [PINS]]  write the pins a deployment builds from
    upstream.py resolve release|prerelease         print the newest pins of that channel
    upstream.py check [LOCK]                       fail unless LOCK pins published releases
"""

import json
import subprocess
import sys
from pathlib import Path

REPOSITORIES = ("processor", "projects")
LOCK = Path("releases.lock.json")
CHOSEN = Path(".bundle/upstream.json")
CHANNELS = ("release", "prerelease")
#: How many of a repository's newest releases ``check`` looks through for a pin.
RECENT = 30


def lock_path() -> Path:
    """The pins this build uses: the ones deploy.sh chose, or production's."""
    return CHOSEN if CHOSEN.is_file() else LOCK


def read_pins() -> dict:
    return json.loads(lock_path().read_text())


def gh(*args: str) -> str:
    return subprocess.check_output(["gh", *args], text=True).strip()


def repository(name: str) -> str:
    return f"opensiddur/opensiddur-{name}"


def releases(name: str) -> list[dict]:
    """A repository's published releases, newest first (drafts are never included)."""
    listed = json.loads(gh("api", f"repos/{repository(name)}/releases?per_page={RECENT}"))
    return [r for r in listed if not r.get("draft")]


def commit(name: str, tag: str) -> str:
    return gh("api", f"repos/{repository(name)}/commits/{tag}", "--jq", ".sha")


def resolve(channel: str) -> dict:
    """The newest pins of a channel: full releases only, or prereleases as well."""
    if channel not in CHANNELS:
        raise SystemExit(f"Unknown channel {channel!r}: use one of {', '.join(CHANNELS)}")
    pins: dict = {}
    tags: dict = {}
    for name in REPOSITORIES:
        candidates = [r for r in releases(name)
                      if channel == "prerelease" or not r.get("prerelease")]
        if not candidates:
            raise SystemExit(f"opensiddur-{name} has no published release")
        tags[name] = candidates[0]["tag_name"]
        pins[name] = commit(name, tags[name])
    return pins | {"tags": tags, "channel": channel}


def check(lock: Path = LOCK) -> list[str]:
    """What is wrong with a lock that must pin published, full releases of both."""
    pins = json.loads(lock.read_text())
    problems = []
    for name in REPOSITORIES:
        pin = pins.get(name, "")
        full = [r["tag_name"] for r in releases(name) if not r.get("prerelease")]
        if not any(commit(name, tag) == pin for tag in full):
            problems.append(
                f"{lock}: opensiddur-{name} {pin or '(missing)'} is not one of its "
                f"{len(full)} most recent published releases ({', '.join(full) or 'none'}); "
                "production pins full releases only"
            )
    return problems


def choose(environment: str, version: str = "", given: str = "") -> dict:
    """Write the pins a deployment builds from to .bundle/upstream.json, and return them.

    A release, and anything deployed to production, uses releases.lock.json, which must
    pin published releases. Any other development deployment uses the pins it is given
    (the daily job resolves them first), or else the newest release or prerelease.
    """
    if environment == "prod" or version:
        problems = check(LOCK)
        if problems:
            raise SystemExit("\n".join(problems))
        pins = json.loads(LOCK.read_text())
    elif given:
        pins = json.loads(Path(given).read_text())
    else:
        pins = resolve("prerelease")
    for name in REPOSITORIES:
        pin = pins.get(name, "")
        if len(pin) != 40 or any(c not in "0123456789abcdef" for c in pin):
            raise SystemExit(f"opensiddur-{name} must be pinned to a full commit hash")
    CHOSEN.parent.mkdir(parents=True, exist_ok=True)
    CHOSEN.write_text(json.dumps(pins, indent=2) + "\n")
    return pins


def main(argv: list[str]) -> int:
    if 2 <= len(argv) <= 4 and argv[0] == "choose":
        choose(*argv[1:])
        return 0
    if len(argv) == 2 and argv[0] == "resolve":
        print(json.dumps(resolve(argv[1]), indent=2))
        return 0
    if argv and argv[0] == "check" and len(argv) <= 2:
        problems = check(Path(argv[1]) if len(argv) == 2 else LOCK)
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1 if problems else 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
