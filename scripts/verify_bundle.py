import json
import os
import subprocess
import tempfile
from pathlib import Path
import yaml
from opensiddur.exporter.settings import validate_settings

processor = Path(os.environ.get("PROCESSOR_DIR", "/opt/processor"))
projects = processor / "opensiddur-projects/project"
bundle = Path(os.environ.get("BUNDLE_DIR", "/opt/bundle"))
catalog = json.loads((bundle / "catalog.json").read_text())
assert catalog["projects"], "Empty catalog"
for project in catalog["projects"]:
    for preset in project["presets"]:
        validate_settings(preset["settings"], project_directory=projects)
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    settings = {
        "book": {"project": "infra_demo", "file_name": "index.xml"},
        "priority": {"transclusion": ["tanakh-wlc-he"]},
        "distribution": {"notice": "none", "back_notice": "none"},
    }
    path = root / "settings.yaml"
    path.write_text(yaml.safe_dump(settings))
    subprocess.run(
        [
            "python",
            "-m",
            "opensiddur.exporter.compiler",
            "-s",
            str(path),
            "-o",
            str(root / "print.xml"),
        ],
        check=True,
    )
    subprocess.run(
        [
            "python",
            "-m",
            "opensiddur.exporter.pdf.pdf",
            str(root / "print.xml"),
            str(root / "sample.pdf"),
            "-s",
            str(path),
        ],
        check=True,
    )
    subprocess.run(
        [
            "python",
            "-m",
            "opensiddur.exporter.compiler",
            "-s",
            str(path),
            "--destination",
            "electronic",
            "-o",
            str(root / "electronic.xml"),
        ],
        check=True,
    )
    subprocess.run(
        [
            "python",
            "-m",
            "opensiddur.exporter.html.html",
            str(root / "electronic.xml"),
            str(root / "sample.html"),
            "-s",
            str(path),
        ],
        check=True,
    )
    assert (root / "sample.pdf").stat().st_size > 100
    assert (root / "sample.html").stat().st_size > 100
print("Catalog, presets, print/electronic compiler, HTML, and PDF smoke checks passed")
