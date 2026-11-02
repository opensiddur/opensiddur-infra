"""Adapter around the pinned upstream processor, never a second settings implementation."""

import json
from pathlib import Path


class Processor:
    def __init__(self, config):
        self.config = config
        self.root = Path(config.bundle)

    def catalog(self):
        return json.loads((self.root / "catalog.json").read_text())

    def schema(self):
        from opensiddur.exporter.settings import SettingsYaml

        return SettingsYaml.model_json_schema()

    def validate(self, data):
        from opensiddur.exporter.settings import validate_settings

        project_root = Path(self.config.processor) / "opensiddur-projects/project"
        data = json.loads(json.dumps(data))
        book = data.get("book") or {}
        project, filename = book.get("project", ""), book.get("file_name", "index.xml")
        target = (project_root / project / filename).resolve()
        allowed = {(p["id"], f) for p in self.catalog()["projects"] for f in p["files"]}
        if (project, filename) not in allowed or not target.is_relative_to(
            project_root.resolve()
        ):
            raise ValueError("Choose a cataloged project and entry point")
        logo = data.get("distribution", {}).get("notice") or {}
        if isinstance(logo, dict) and logo.get("logo", "default") not in {
            "default",
            "none",
        }:
            raise ValueError(
                "Use the managed logo upload control instead of a filesystem path"
            )
        result = validate_settings(
            data, project_directory=project_root, resolve_fonts=True
        )
        return result.model_dump(mode="json", exclude_unset=True)
