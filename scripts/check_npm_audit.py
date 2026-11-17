"""Check npm audit, with one temporary exception for development tooling."""

import json
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADVISORY = "https://github.com/advisories/GHSA-fc5q-39xc-vjpf"
EXPIRES = date(2026, 12, 1)


def check_report(report, lock, today):
    """Resolve npm's propagated findings to their underlying advisories."""
    if today >= EXPIRES:
        raise ValueError(
            f"picomatch exception expired on {EXPIRES}; remove or review it"
        )
    if report.get("auditReportVersion") != 2 or "error" in report:
        raise ValueError("npm audit did not return a supported audit report")
    findings = report["vulnerabilities"]

    def accepted(name, ancestors):
        if name in ancestors:
            return False
        finding = findings[name]
        if finding["severity"] in {"info", "low", "moderate"}:
            return True
        if finding["severity"] != "high":
            return False
        # The exception is restricted to locked development dependencies.
        if not finding["nodes"] or any(
            lock["packages"][node].get("dev") is not True for node in finding["nodes"]
        ):
            return False
        if not finding["via"]:
            return False
        for cause in finding["via"]:
            if isinstance(cause, str):
                if not accepted(cause, ancestors | {name}):
                    return False
            elif not (
                name == "picomatch"
                and finding["severity"] == "high"
                and cause["name"] == cause["dependency"] == "picomatch"
                and cause["url"] == ADVISORY
                and cause["severity"] == "high"
                and cause["range"] == "<=4.0.7"
                and all(
                    lock["packages"][node]["version"] == "4.0.7"
                    for node in finding["nodes"]
                )
            ):
                return False
        return True

    rejected = [name for name in findings if not accepted(name, set())]
    if rejected:
        raise ValueError("Unexcepted npm vulnerabilities: " + ", ".join(rejected))


def main():
    # Production retains npm's native high/critical gate, without exceptions.
    subprocess.run(
        ["npm", "--prefix", "web", "audit", "--omit=dev", "--audit-level=high"],
        cwd=ROOT,
        check=True,
    )
    result = subprocess.run(
        ["npm", "--prefix", "web", "audit", "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    print(result.stdout)
    if result.returncode not in {0, 1}:
        raise ValueError(f"npm audit failed: {result.stderr}")
    check_report(
        json.loads(result.stdout),
        json.loads((ROOT / "web/package-lock.json").read_text()),
        datetime.now(UTC).date(),
    )
    print(
        f"npm audit passed; development-only exception: {ADVISORY} until {EXPIRES} UTC"
    )


if __name__ == "__main__":
    main()
