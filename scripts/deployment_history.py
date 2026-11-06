"""Keep immutable worker image history in the protected state bucket across CI runs."""

import json
import subprocess
import sys
from pathlib import Path

mode, bucket, config_path = sys.argv[1:]
config = Path(config_path)
remote = f"gs://{bucket}/deployments/releases.json"
if mode == "load":
    result = subprocess.run(
        ["gcloud", "storage", "cat", remote], capture_output=True, text=True
    )
    if result.returncode == 0:
        history = json.loads(result.stdout)
        lines = [
            line
            for line in config.read_text().splitlines()
            if not line.startswith("release_images =")
        ]
        config.write_text(
            "\n".join(lines) + "\nrelease_images = " + json.dumps(history) + "\n"
        )
    elif (
        "not found" not in result.stderr.lower()
        and "notfound" not in result.stderr.lower()
        and "matched no objects" not in result.stderr.lower()
    ):
        raise SystemExit("Cannot read deployment history: " + result.stderr)
else:
    import re

    match = re.search(r"^release_images = (.+)$", config.read_text(), re.M)
    path = config.parent / "release-history.json"
    path.write_text(match.group(1) if match else "{}")
    subprocess.run(["gcloud", "storage", "cp", str(path), remote], check=True)
