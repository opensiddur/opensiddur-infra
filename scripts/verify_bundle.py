"""Exercise the real unprivileged worker, including all four output types and ZIP publication."""

import json
import os
import uuid
from dataclasses import replace
from pathlib import Path

from opensiddur.exporter.settings import validate_settings
from opensiddur_infra.builds import Builds
from opensiddur_infra.config import Config
from opensiddur_infra.store import MemoryStore
from opensiddur_infra.worker import execute, preview_app
from opensiddur_infra.api import create_app
from opensiddur_infra.processor import Processor

processor = Path(os.environ.get("PROCESSOR_DIR", "/opt/processor"))
projects = processor / "opensiddur-projects/project"
bundle = Path(os.environ.get("BUNDLE_DIR", "/opt/bundle"))
catalog = json.loads((bundle / "catalog.json").read_text())
assert catalog["projects"], "Empty catalog"
for project in catalog["projects"]:
    for preset in project["presets"]:
        validate_settings(preset["settings"], project_directory=projects)


class Outputs:
    def __init__(self):
        self.files = {}

    def put(self, name, data, content_type):
        self.files[name.rsplit("/", 1)[-1]] = data
        return {
            "name": name.rsplit("/", 1)[-1],
            "object": name,
            "size": len(data),
            "content_type": content_type,
        }

    def delete_prefix(self, prefix):
        self.files.clear()


settings = {
    "book": {"project": "infra_demo", "file_name": "index.xml"},
    "priority": {"transclusion": ["tanakh-wlc-he"]},
    "distribution": {"notice": "none", "back_notice": "none"},
}
store, outputs = MemoryStore(), Outputs()
owner = str(uuid.uuid4())
key = "account:" + owner
store.atomic(
    [key],
    lambda rows: rows.update(
        {
            key: {
                "kind": "account",
                "owner": owner,
                "enabled": True,
                "consent": {"version": "smoke"},
            }
        }
    ),
)
config = replace(Config(), release=catalog["release"])
adapter = Processor(config)
for project in catalog["projects"]:
    for preset in project["presets"]:
        canonical = adapter.validate(preset["settings"])
        validate_settings(canonical, project_directory=projects)
        assert canonical == adapter.validate(canonical), (
            "Settings canonicalization must round-trip"
        )
assert preview_app().routes
assert create_app(config=config, store=store, storage=outputs).routes
builds = Builds(store, config.release)
row = builds.submit(
    owner, settings, ["html", "pdf", "tex", "xml"], "full", "container-smoke"
)
os.environ["SAMPLE_DIAGNOSTICS"] = "true"
execute(row["id"], config, store, outputs)
finished = builds.get(owner, row["id"])
assert finished["state"] == "succeeded", finished["results"]
for name in (
    "book.pdf",
    "book.html",
    "book.tex",
    "compiled-print.xml",
    "compiled-electronic.xml",
    "artifacts.zip",
    "settings.yaml",
    "manifest.json",
    "software-notices.json",
):
    assert len(outputs.files.get(name, b"")) > 0, name
assert outputs.files["book.pdf"].startswith(b"%PDF")
print(
    "Actual unprivileged worker: catalog/preset validation, private SQLite, PDF, HTML, TeX, XML, ZIP and publication all passed"
)
