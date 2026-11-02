"""Content identity shared by deployment and image assembly (independent of .git)."""

import hashlib
from pathlib import Path


def release_identity():
    roots = [Path("app"), Path("scripts"), Path("web/src"), Path("web/public")]
    files = [
        Path(x)
        for x in (
            "Dockerfile",
            "uv.lock",
            "releases.lock.json",
            "web/package-lock.json",
        )
    ]
    files += [
        p
        for root in roots
        for p in root.rglob("*")
        if p.suffix in {".py", ".sh", ".mjs", ".ts", ".tsx", ".css", ".svg", ".txt"}
    ]
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(str(path).encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()[:20]


if __name__ == "__main__":
    print(release_identity())
