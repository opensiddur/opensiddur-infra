"""Update pinned refs only when both repositories have a published release."""

import json
import subprocess
from pathlib import Path


def gh(*args):
    return subprocess.check_output(["gh", *args], text=True).strip()


commits = {}
for name in ("processor", "projects"):
    repo = "opensiddur/opensiddur-" + name
    try:
        tag = gh(
            "release", "view", "--repo", repo, "--json", "tagName", "--jq", ".tagName"
        )
    except subprocess.CalledProcessError:
        print(f"No published {name} release; keeping current bundle")
        raise SystemExit(0)
    commits[name] = gh("api", f"repos/{repo}/commits/{tag}", "--jq", ".sha")
lock = Path("releases.lock.json")
old = json.loads(lock.read_text())
if any(old.get(k) != v for k, v in commits.items()):
    lock.write_text(
        json.dumps(commits | {"channel": "published-releases"}, indent=2) + "\n"
    )
