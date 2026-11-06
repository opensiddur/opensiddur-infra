"""Infra's lock owns shared packages; upstream's lock supplies missing packages.

Both inputs are pinned. uv pip check and the image smoke test reject incompatible
combinations rather than silently downgrading the web/auth stack.
"""

import importlib.metadata
import sys
from pathlib import Path

import re


def canonicalize_name(name):
    return re.sub(r"[-_.]+", "-", name).lower()


installed = {
    canonicalize_name(d.metadata["Name"]) for d in importlib.metadata.distributions()
}
chunks = []
current = []
for line in Path(sys.argv[1]).read_text().splitlines():
    if not line.strip() or line.lstrip().startswith("#"):
        continue
    current.append(line)
    if not line.rstrip().endswith("\\"):
        chunks.append("\n".join(current))
        current = []
result = []
for chunk in chunks:
    match = re.match(r"([A-Za-z0-9_.-]+)", chunk)
    if not match:
        raise ValueError("Unrecognized pinned requirement")
    if canonicalize_name(match.group(1)) not in installed:
        result.append(chunk)
Path(sys.argv[2]).write_text("\n".join(result) + "\n")
