"""The temporary audit exception must not hide other security findings."""

import importlib.util
import json
import subprocess
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_npm_audit", ROOT / "scripts/check_npm_audit.py"
)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


@pytest.fixture
def data():
    cause = {
        "name": "picomatch",
        "dependency": "picomatch",
        "url": audit.ADVISORY,
        "severity": "high",
        "range": "<=4.0.7",
    }
    findings = {}
    packages = {}
    for name, via in [
        ("picomatch", [cause]),
        ("fdir", ["picomatch"]),
        ("tinyglobby", ["picomatch", "fdir"]),
        ("vite", ["picomatch", "tinyglobby"]),
        ("vitest", ["picomatch", "tinyglobby", "vite"]),
        ("@vitejs/plugin-react", ["vite"]),
    ]:
        node = f"node_modules/{name}"
        findings[name] = {"severity": "high", "via": via, "nodes": [node]}
        packages[node] = {"dev": True, "version": "4.0.7"}
    return {"auditReportVersion": 2, "vulnerabilities": findings}, {
        "packages": packages
    }


def check(data, today=date(2026, 11, 17)):
    audit.check_report(*data, today)


def test_exception_covers_propagation_and_last_valid_day(data):
    check(data, audit.EXPIRES - timedelta(days=1))


@pytest.mark.parametrize("offset", [0, 1, 365])
def test_exception_expires(data, offset):
    with pytest.raises(ValueError, match="expired"):
        check(data, audit.EXPIRES + timedelta(days=offset))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("url", "https://github.com/advisories/GHSA-other"),
        ("name", "other"),
        ("dependency", "other"),
        ("severity", "critical"),
        ("range", "<=4.0.8"),
    ],
)
def test_exception_requires_exact_advisory(data, field, value):
    data[0]["vulnerabilities"]["picomatch"]["via"][0][field] = value
    with pytest.raises(ValueError, match="Unexcepted"):
        check(data)


@pytest.mark.parametrize("name", ["picomatch", "vite"])
@pytest.mark.parametrize("dev", [False, None])
def test_exception_never_covers_production(data, name, dev):
    data[1]["packages"][f"node_modules/{name}"]["dev"] = dev
    with pytest.raises(ValueError, match="Unexcepted"):
        check(data)


def test_exception_does_not_expand_to_other_versions(data):
    data[1]["packages"]["node_modules/picomatch"]["version"] = "4.0.8"
    with pytest.raises(ValueError, match="Unexcepted"):
        check(data)


def test_second_advisory_on_same_package_is_rejected(data):
    causes = data[0]["vulnerabilities"]["picomatch"]["via"]
    causes.append({**causes[0], "url": "https://github.com/advisories/GHSA-other"})
    with pytest.raises(ValueError, match="Unexcepted"):
        check(data)


@pytest.mark.parametrize("severity", ["high", "critical", "unknown"])
def test_unrelated_findings_are_rejected(data, severity):
    data[0]["vulnerabilities"]["vite"]["severity"] = severity
    data[0]["vulnerabilities"]["vite"]["via"].append(
        {"name": "vite", "url": "https://github.com/advisories/GHSA-other"}
    )
    with pytest.raises(ValueError, match="Unexcepted"):
        check(data)


def test_cycle_fails_closed(data):
    data[0]["vulnerabilities"]["picomatch"]["via"] = ["vite"]
    with pytest.raises(ValueError, match="Unexcepted"):
        check(data)


@pytest.mark.parametrize(
    "report",
    [{}, {"auditReportVersion": 3}, {"auditReportVersion": 2, "error": {}}],
)
def test_invalid_audit_fails_closed(data, report):
    with pytest.raises(ValueError):
        audit.check_report(report, data[1], date(2026, 11, 17))


def test_clean_report_passes(data):
    data[0]["vulnerabilities"] = {}
    check(data)


def test_moderate_findings_preserve_existing_threshold(data):
    finding = data[0]["vulnerabilities"]["vite"]
    finding.update(severity="moderate", via=[{"url": "other"}])
    check(data)


def test_audit_execution_error_cannot_pass(monkeypatch, data):
    results = iter(
        [
            None,
            SimpleNamespace(returncode=2, stdout=json.dumps(data[0]), stderr="error"),
        ]
    )
    monkeypatch.setattr(audit.subprocess, "run", lambda *a, **kw: next(results))
    with pytest.raises(ValueError, match="npm audit failed"):
        audit.main()


def test_production_audit_failure_stops_before_exception(monkeypatch):
    def fail(command, **kwargs):
        assert "--omit=dev" in command
        assert kwargs["check"] is True
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(audit.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        audit.main()
