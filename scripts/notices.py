#!/usr/bin/env python3
"""Publish license texts present in installed distributions and Debian copyright files."""

import importlib.metadata
import json
import os
from pathlib import Path


def generate(bundle, processor):
    release = json.loads((bundle / "release.json").read_text())
    components = []
    for distribution in importlib.metadata.distributions():
        meta = distribution.metadata
        texts = []
        for item in distribution.files or []:
            if any(
                x in item.name.lower()
                for x in ("license", "licence", "copying", "notice")
            ) and ".dist-info" in str(item):
                path = Path(distribution.locate_file(item))
                if path.is_file():
                    texts.append(path.read_text(errors="replace"))
        components.append(
            {
                "name": meta["Name"],
                "version": meta["Version"],
                "license": meta.get("License-Expression")
                or meta.get("License")
                or "Review upstream license texts",
                "source": meta.get("Home-page")
                or f"https://pypi.org/project/{meta['Name']}/{meta['Version']}/",
                "text": "\n\n".join(texts),
            }
        )
    for path in Path("/usr/share/doc").glob("*/copyright"):
        components.append(
            {
                "name": path.parent.name,
                "version": "container package",
                "license": "See Debian copyright and license notices",
                "source": "https://packages.debian.org/" + path.parent.name,
                "text": path.read_text(errors="replace"),
            }
        )
    common = Path("/usr/share/common-licenses")
    for path in common.iterdir() if common.exists() else []:
        if path.is_file():
            components.append(
                {
                    "name": path.name,
                    "version": "license text",
                    "license": path.name,
                    "source": "https://www.debian.org/legal/licenses/",
                    "text": path.read_text(errors="replace"),
                }
            )
    for name, root, sha in (
        ("opensiddur-infra", Path.cwd(), release.get("infra_commit", "development")),
        ("opensiddur-processor", processor, release["processor"]),
    ):
        components.append(
            {
                "name": name,
                "version": sha,
                "license": "LGPL-3.0-or-later",
                "source": f"https://github.com/opensiddur/{name}/tree/{sha}",
                "text": (root / "LICENSE").read_text(),
            }
        )
    components.append(
        {
            "name": "Open Siddur Project logo",
            "version": "2016 SVG, unchanged",
            "license": "CC-BY-SA-4.0",
            "source": "https://opensiddur.org/wp-content/uploads/2018/09/Open-Siddur-Project-Logo-2016.svg",
            "text": Path("web/public/brand-notice.txt").read_text(),
        }
    )
    font_docs = Path("/usr/share/doc/opensiddur-font-pack")
    if (font_docs / "manifest.json").exists():
        font_manifest = json.loads((font_docs / "manifest.json").read_text())
        texts = [
            str(path.relative_to(font_docs)) + "\n" + path.read_text(errors="replace")
            for path in sorted(font_docs.rglob("*"))
            if path.is_file() and path.name != "manifest.json"
        ]
        components.append(
            {
                "name": "Open Siddur font pack",
                "version": font_manifest["revision"],
                "license": "Multiple font licenses; see included per-font notices",
                "source": font_manifest["repository"].removesuffix(".git")
                + "/tree/"
                + font_manifest["revision"],
                "text": "\n\n".join(texts),
            }
        )
    frontend = Path(".bundle/frontend-notices.json")
    if frontend.exists():
        components.extend(json.loads(frontend.read_text()))
    return {"release": release["release"], "components": components}


if __name__ == "__main__":
    bundle = Path(os.environ.get("BUNDLE_DIR", "/opt/bundle"))
    (bundle / "notices.json").write_text(
        json.dumps(
            generate(bundle, Path(os.environ.get("PROCESSOR_DIR", "/opt/processor"))),
            ensure_ascii=False,
        )
    )
