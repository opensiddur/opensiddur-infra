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
        if not isinstance(data, dict):
            raise ValueError("Settings must be a mapping")
        book = data.get("book") or {}
        if not isinstance(book, dict):
            raise ValueError("book must be a mapping")
        project, filename = book.get("project", ""), book.get("file_name", "index.xml")
        if not isinstance(project, str) or not isinstance(filename, str):
            raise ValueError("Choose a cataloged project and entry point")
        catalog = self.catalog()["projects"]
        allowed_projects = {p["id"] for p in catalog}
        target = (project_root / project / filename).resolve()
        allowed = {(p["id"], f) for p in catalog for f in p["files"]}
        if (project, filename) not in allowed or not target.is_relative_to(
            project_root.resolve()
        ):
            raise ValueError("Choose a cataloged project and entry point")
        priority = data.get("priority") or {}
        parallel = data.get("parallel") or {}
        if not isinstance(priority, dict) or not isinstance(parallel, dict):
            raise ValueError("Source settings must be mappings")
        for sources in [
            priority.get("transclusion", []),
            priority.get("instructions", []),
            parallel.get("projects", []),
            data.get("annotations", []),
        ]:
            if not isinstance(sources, list) or any(
                not isinstance(p, str) or p not in allowed_projects for p in sources
            ):
                raise ValueError("All source selections must come from the catalog")
        distribution = data.get("distribution") or {}
        if not isinstance(distribution, dict):
            raise ValueError("distribution must be a mapping")
        logo = distribution.get("notice") or {}
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
