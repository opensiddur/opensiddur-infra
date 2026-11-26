#!/usr/bin/env python3
"""The opensiddur-processor and opensiddur-projects commits a runtime is built from.

Nothing is pinned in the repository; each deployment finds its commits when it runs:

- development (https://opensiddur-builder-dev.web.app/), unless it is a release's
  development stage, follows the ``main`` branch of each repository;
- a release, in every stage, and production
  (https://opensiddur-builder-prod.web.app/) use the newest published, full release of
  each. A release run resolves them once and passes them to each stage, which checks them.

``deploy.sh`` writes the pins it chose (``choose``) to ``.bundle/upstream.json``; the image
build (``fetch_sources.py``, ``bundle.py``) and the release ID read that file.

    upstream.py choose ENVIRONMENT [VERSION [PINS]]  write the pins a deployment builds from
    upstream.py resolve release|main               print the newest pins of that channel
    upstream.py check PINS                         fail unless PINS are full releases
"""

import json
import subprocess
import sys
from pathlib import Path

REPOSITORIES = ("processor", "projects")
CHOSEN = Path(".bundle/upstream.json")
CHANNELS = ("release", "main")
#: How many of a repository's releases ``resolve`` looks through for the newest.
RECENT = 30


def read_pins() -> dict:
    """The pins this build uses: the ones ``choose`` wrote."""
    if not CHOSEN.is_file():
        raise SystemExit(
            f"No upstream pins in {CHOSEN}: run `python3 scripts/upstream.py choose dev` "
            "(the main branches) or `choose prod` (the newest releases) first"
        )
    return json.loads(CHOSEN.read_text())


def gh(*args: str) -> str:
    return subprocess.check_output(["gh", *args], text=True).strip()


def repository(name: str) -> str:
    return f"opensiddur/opensiddur-{name}"


def releases(name: str) -> list[dict]:
    """A repository's recent published releases, newest first (never drafts).

    GitHub lists releases by the date of their commit; a release cut from an older commit
    would sort below a newer one, so they are sorted by when they were published.
    """
    listed = json.loads(
        gh("api", f"repos/{repository(name)}/releases?per_page={RECENT}")
    )
    published = [r for r in listed if not r.get("draft")]
    return sorted(published, key=lambda r: r.get("published_at") or "", reverse=True)


def release(name: str, tag: str) -> dict:
    return json.loads(gh("api", f"repos/{repository(name)}/releases/tags/{tag}"))


def commit(name: str, ref: str) -> str:
    return gh("api", f"repos/{repository(name)}/commits/{ref}", "--jq", ".sha")


def resolve(channel: str) -> dict:
    """The newest pins of a channel: the newest full releases, or the main branches."""
    if channel not in CHANNELS:
        raise SystemExit(
            f"Unknown channel {channel!r}: use one of {', '.join(CHANNELS)}"
        )
    if channel == "main":
        pins = {name: commit(name, "main") for name in REPOSITORIES}
        return pins | {"branch": "main", "channel": channel}
    pins = {}
    tags = {}
    for name in REPOSITORIES:
        full = [r for r in releases(name) if not r.get("prerelease")]
        if not full:
            raise SystemExit(f"opensiddur-{name} has no published release")
        tags[name] = full[0]["tag_name"]
        pins[name] = commit(name, tags[name])
    return pins | {"tags": tags, "channel": channel}


def check(pins: dict, where: str = "pins") -> list[str]:
    """What is wrong with pins that must be published, full releases of both.

    The pins name each release (``tags``); its commit must be that release's commit.
    """
    tags = pins.get("tags") or {}
    problems = []
    for name in REPOSITORIES:
        pin, tag = pins.get(name, ""), tags.get(name, "")
        label = f"{where}: opensiddur-{name}"
        if not pin or not tag:
            problems.append(
                f"{label} needs both a commit and its release tag (tags.{name})"
            )
            continue
        try:
            found = release(name, tag)
        except subprocess.CalledProcessError:
            problems.append(f"{label}: {tag} is not a published release")
            continue
        if found.get("draft") or found.get("prerelease"):
            problems.append(
                f"{label}: {tag} is a prerelease or draft; releases and production "
                "use full releases only"
            )
        elif commit(name, tag) != pin:
            problems.append(f"{label}: {pin} is not the commit of release {tag}")
    return problems


def choose(environment: str, version: str = "", given: str = "") -> dict:
    """Write the pins a deployment builds from to .bundle/upstream.json, and return them.

    A release (any deployment with a version) and production use full releases: the
    pins they are given, which must be full releases, or else the newest. Any other
    development deployment uses the pins it is given, or else the main branches.
    """
    supplied = json.loads(Path(given).read_text()) if given else None
    if environment == "prod" or version:
        if supplied is None:
            pins = resolve("release")
        else:
            problems = check(supplied, given)
            if problems:
                raise SystemExit("\n".join(problems))
            pins = supplied
    else:
        pins = supplied if supplied is not None else resolve("main")
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
    if len(argv) == 2 and argv[0] == "check":
        problems = check(json.loads(Path(argv[1]).read_text()), argv[1])
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1 if problems else 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
