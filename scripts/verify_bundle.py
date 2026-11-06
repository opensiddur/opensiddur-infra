"""Exercise the real unprivileged worker, including all four output types and ZIP publication."""

import json
import os
import subprocess
import tempfile
import uuid
from dataclasses import replace
from pathlib import Path

from lxml import etree
from opensiddur.exporter.derived_settings import STATIC_DEFAULTS
from opensiddur.exporter.settings import validate_settings
from opensiddur.exporter.typography import resolve_font
from opensiddur_infra.api import create_app
from opensiddur_infra.builds import Builds
from opensiddur_infra.config import Config
from opensiddur_infra.processor import Processor
from opensiddur_infra.store import MemoryStore
from opensiddur_infra.worker import (
    execute,
    prepare_tex_cache,
    preview_app,
    tex_environment,
)

processor = Path(os.environ.get("PROCESSOR_DIR", "/opt/processor"))
projects = processor / "opensiddur-projects/project"
bundle = Path(os.environ.get("BUNDLE_DIR", "/opt/bundle"))
catalog = json.loads((bundle / "catalog.json").read_text())
assert catalog["projects"], "Empty catalog"
assert catalog["declaration_defaults"] == STATIC_DEFAULTS, (
    "Customs defaults must match the pinned compiler"
)
font_catalog = catalog["font_catalog"]
assert font_catalog["hebrew"] and font_catalog["latin"][0]["fonts"]
for family in font_catalog["installed"]:
    assert resolve_font([family]) == family, family
font_manifest = json.loads(
    Path("/usr/share/doc/opensiddur-font-pack/manifest.json").read_text()
)
assert (
    font_manifest["revision"]
    == json.loads(Path("fonts.lock.json").read_text())["revision"]
)
for relative in font_manifest["installed"]:
    assert (Path("/usr/share/fonts/opensiddur-pack") / relative).is_file(), relative
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
    "book": {"project": "preview-he", "file_name": "index.xml"},
    "priority": {"transclusion": ["preview-he", "preview-en"]},
    "parallel": {"projects": ["preview-he", "preview-en"]},
    # Exercise the default notice/logo under the same restricted TeX policy as users.
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
    "worker.log",
    "pdf.log",
    "logo.png",
):
    assert len(outputs.files.get(name, b"")) > 0, name
assert outputs.files["book.pdf"].startswith(b"%PDF")
assert b"@font-face" not in outputs.files["book.html"]
preview_settings = settings | {
    "typography": {"fonts": {"latin": ["DejaVu Sans", "Liberation Serif"]}},
}
preview_outputs = Outputs()
preview_row = builds.submit(owner, preview_settings, ["html"], "html", "font-smoke")
execute(preview_row["id"], config, store, preview_outputs)
preview_finished = builds.get(owner, preview_row["id"])
assert preview_finished["state"] == "succeeded", preview_finished["results"]
html_preview = preview_outputs.files["preview.html"]
assert b'--font-latin: "DejaVu Sans", "Liberation Serif", serif;' in html_preview
for family in (b"DejaVu Sans", b"Liberation Serif"):
    assert (
        b'@font-face { font-family: "' + family + b'"; src: url("data:font/'
        in html_preview
    )
pdf_step = next(step for step in finished["steps"] if step["id"] == "pdf")
assert pdf_step["pass_number"] >= 1, pdf_step
assert all(step["state"] == "succeeded" for step in finished["steps"]), finished[
    "steps"
]
assert b"{logo.png}" in outputs.files["book.tex"], (
    "TeX logo must remain portable and sandbox-compatible"
)
tex = outputs.files["book.tex"].decode()
sample_text = "A demonstration passage shown when a minyan is selected."
sample_position = tex.index(sample_text)
assert r"\setdefaultlanguage{english}" in tex
prefix = tex[:sample_position]
assert prefix.count(r"\begin{hebrew}") == prefix.count(r"\end{hebrew}"), (
    "English sample text must be outside the RTL Hebrew stream"
)
xml = etree.fromstring(outputs.files["compiled-print.xml"])
assert xml.xpath("//*[local-name()='parallel']"), (
    "Preview must exercise parallel layout"
)
assert xml.xpath("//*[local-name()='titlePage']"), "Preview must exercise title pages"
assert xml.xpath("//*[local-name()='list']"), "Preview must exercise lists"


# Exercise the real Lua IO policy as the unprivileged image user. New TeX needs
# installed Unicode tables, but must not gain access to credentials or other runs.
with (
    tempfile.TemporaryDirectory(prefix="tex-policy-") as directory,
    tempfile.TemporaryDirectory(prefix="other-build-") as other,
):
    work = Path(directory)
    assert Path("/usr/share/opensiddur-tex-cache").is_dir(), (
        "Image must initialize fonts"
    )
    prepare_tex_cache(work)
    secret = Path(other) / "private.txt"
    secret.write_text("another build's private data")
    source = r"""\documentclass{article}
\begin{document}
\directlua{
assert(io.open('/etc/passwd', 'r') == nil)
assert(io.open('OTHER_FILE', 'r') == nil)
assert(io.open('/usr/share/opensiddur-write-probe', 'w') == nil)
local f = assert(io.open('private-output.txt', 'w')); f:write('ok'); f:close()
}
Policy check.
\end{document}
""".replace("OTHER_FILE", str(secret))
    (work / "policy.tex").write_text(source)
    result = subprocess.run(
        ["lualatex", "-interaction=nonstopmode", "-halt-on-error", "policy.tex"],
        cwd=work,
        env=os.environ | tex_environment(work),
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout.decode(errors="replace")[-4000:]
    assert (work / "private-output.txt").read_text() == "ok"
print(
    "Actual unprivileged worker: catalog/preset validation, private SQLite, PDF, HTML, TeX, XML, ZIP and publication all passed"
)
