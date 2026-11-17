"""Exercise the actual privileged workflow's policy without GitHub writes."""

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = yaml.safe_load(
    (ROOT / ".github/workflows/dependabot-automerge.yml").read_text()
)
POLICY = next(
    step["run"]
    for step in WORKFLOW["jobs"]["enable-auto-merge"]["steps"]
    if step.get("id") == "policy"
)


def dependency(**changes):
    return {
        "dependencyName": "pytest",
        "dependencyType": "direct:development",
        "updateType": "version-update:semver-patch",
        "targetBranch": "main",
        "maintainerChanges": False,
        "packageEcosystem": "uv",
        "directory": "/",
        **changes,
    }


@pytest.mark.parametrize(
    ("metadata", "eligible"),
    [
        ([dependency()], True),
        ([dependency(), dependency(dependencyName="ruff")], True),
        (
            [
                dependency(
                    dependencyName="@types/react",
                    packageEcosystem="npm_and_yarn",
                    directory="/web",
                )
            ],
            True,
        ),
        ([dependency(), dependency(dependencyName="fastapi")], False),
        ([dependency(dependencyName="pytest-extra")], False),
        ([dependency(dependencyType="direct:production")], False),
        ([dependency(dependencyType="indirect")], False),
        ([dependency(updateType="version-update:semver-minor")], False),
        ([dependency(updateType="version-update:semver-major")], False),
        ([dependency(targetBranch="release")], False),
        ([dependency(maintainerChanges=True)], False),
        ([dependency(packageEcosystem="terraform")], False),
        ([dependency(packageEcosystem="github_actions")], False),
        ([dependency(directory="/other")], False),
        ([dependency(dependencyName="@types/react")], False),
        ([{}], False),
        ([], False),
        ({}, False),
        (None, False),
        ("invalid json", False),
    ],
)
def test_auto_merge_policy(tmp_path, metadata, eligible):
    output = tmp_path / "output"
    subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", POLICY],
        env={
            **os.environ,
            "DEPENDENCIES": metadata
            if isinstance(metadata, str)
            else json.dumps(metadata),
            "GITHUB_OUTPUT": str(output),
        },
        check=True,
        capture_output=True,
        text=True,
    )
    assert output.read_text() == f"eligible={str(eligible).lower()}\n"
