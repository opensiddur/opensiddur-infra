#!/usr/bin/env python3
import json
import os
from pathlib import Path

import yaml
from lxml import etree
from opensiddur.exporter.derived_settings import STATIC_DEFAULTS
from opensiddur.exporter.tex.running_heads import RUNNING_HEAD_CODES
from opensiddur_infra.fonts import inventory

processor = Path(os.environ.get("PROCESSOR_DIR", "/opt/processor"))
bundle = Path(os.environ.get("BUNDLE_DIR", "/opt/bundle"))
bundle.mkdir(parents=True, exist_ok=True)
projects = processor / "opensiddur-projects/project"
ns = {"t": "http://www.tei-c.org/ns/1.0"}
lock = json.loads(Path("releases.lock.json").read_text())
from release_id import release_identity

release = release_identity()
fonts = inventory()
result = []
for project in sorted(projects.iterdir()):
    if not (project / "index.xml").exists():
        continue
    tree = etree.parse(str(project / "index.xml"))
    titles = tree.xpath("//t:teiHeader/t:fileDesc/t:titleStmt/t:title", namespaces=ns)
    title = next(
        (
            "".join(t.itertext()).strip()
            for t in titles
            if t.get("{http://www.w3.org/XML/1998/namespace}lang") == "en"
        ),
        "".join(titles[0].itertext()).strip() if titles else project.name,
    )
    presets = []
    for path in sorted(
        (processor / "opensiddur-projects/settings" / project.name).glob("*.yaml")
    ):
        presets.append(
            {"name": path.stem, "settings": yaml.safe_load(path.read_text())}
        )
    result.append(
        {
            "id": project.name,
            "title": title,
            "language": tree.getroot().get(
                "{http://www.w3.org/XML/1998/namespace}lang", ""
            ),
            "description": "",
            "files": [
                str(p.relative_to(project)) for p in sorted(project.rglob("*.xml"))
            ],
            "presets": presets,
            "licenses": tree.xpath("//t:licence/@target", namespaces=ns),
        }
    )
(bundle / "catalog.json").write_text(
    json.dumps(
        {
            "release": release,
            "projects": result,
            "fonts": fonts["installed"],
            "features": yaml.safe_load(
                (processor / "opensiddur/exporter/features.yaml").read_text()
            ),
            "declaration_defaults": STATIC_DEFAULTS,
            "running_head_codes": sorted(RUNNING_HEAD_CODES),
            "font_catalog": fonts,
            "feature_labels": yaml.safe_load(
                (processor / "opensiddur/exporter/html/basic_settings.yaml").read_text()
            ),
        },
        ensure_ascii=False,
    )
)
source = (
    json.loads(Path(".bundle/source.json").read_text())
    if Path(".bundle/source.json").exists()
    else {}
)
(bundle / "release.json").write_text(
    json.dumps(
        {
            "release": release,
            **lock,
            "fonts": json.loads(Path("fonts.lock.json").read_text()),
            **source,
        },
        indent=2,
    )
)
# Fixed, bounded demonstration; only its text source has a declared fallback.
demo = projects / "infra_demo"
demo.mkdir(exist_ok=True)
(demo / "index.xml").write_text(
    """<tei:TEI xmlns:tei="http://www.tei-c.org/ns/1.0" xmlns:j="http://jewishliturgy.org/ns/jlptei/2" xml:lang="he"><tei:teiHeader><tei:fileDesc><tei:titleStmt><tei:title>Open Siddur settings demonstration</tei:title></tei:titleStmt><tei:publicationStmt><tei:availability><tei:licence target="https://creativecommons.org/publicdomain/zero/1.0/">Demonstration wrapper: CC0.</tei:licence></tei:availability></tei:publicationStmt><tei:sourceDesc><tei:p>Text sources are credited in the generated colophon.</tei:p></tei:sourceDesc></tei:fileDesc></tei:teiHeader><tei:text><tei:body><tei:div><tei:head xml:lang="en">Settings demonstration · Psalm 23</tei:head><tei:p><tei:note type="editorial" xml:lang="en">This is a fixed sample. Source priorities apply where the selected editions contain Psalm 23. The sample uses WLC as an explicit fallback.</tei:note></tei:p><j:transclude target="urn:x-opensiddur:text:bible:psalms/23" type="external"/><j:conditional xml:id="sample_minyan"><tei:fs type="opensiddur:quorum"><tei:f name="minyan"><tei:binary value="true"/></tei:f></tei:fs></j:conditional><tei:p xml:lang="en">A demonstration passage shown when a minyan is selected.</tei:p><j:endConditional target="#sample_minyan"/></tei:div></tei:body></tei:text></tei:TEI>"""
)
from notices import generate

(bundle / "notices.json").write_text(
    json.dumps(generate(bundle, processor), ensure_ascii=False)
)
