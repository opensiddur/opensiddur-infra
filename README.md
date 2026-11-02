# Open Siddur hosted builder

A GCP-hosted distribution channel for [opensiddur-processor](https://github.com/opensiddur/opensiddur-processor) and [opensiddur-projects](https://github.com/opensiddur/opensiddur-projects).

Public project browsing and settings editing; verified accounts for compiler previews and full builds. Configure source and translation priorities, annotations, customs and typography. Preview a fixed Psalm 23 demonstration, request a PDF sample, then generate PDF/HTML with advanced TeX/XML exports. Results are private, UUID-addressed, optionally shareable, and expire after 30 days. Explicitly saved presets persist until deleted.

## Development

Requires Python 3.12, uv, Node 24/npm and Terraform 1.13.5. Authentication and storage integration require GCP or test doubles; no fake production authentication is provided.

```bash
uv sync --frozen --python 3.12
uv run pytest
npm --prefix web ci
npm --prefix web test
npm --prefix web run build
terraform -chdir=infrastructure init -backend=false
terraform -chdir=infrastructure validate
```

The Python suite uses synthetic project/settings data. Cloud Build additionally tests the actual pinned catalog, presets and demo PDF/HTML in the worker image before deployment.

## Deployment and operation

- [Deployment, rollback and teardown](docs/deployment.md)
- [Architecture and API](docs/architecture.md)
- [Privacy and account responsibilities](docs/privacy.md)
- [Software licensing](docs/licensing.md)

The default configuration keeps public submissions disabled. The development pilot permits configured operator emails; production requires App Check. Publishing the UI does not open registration for compute use.

Cloud infrastructure is managed with Terraform and deployment scripts. GitHub Actions uses Workload Identity Federation; local scripts use the existing authenticated gcloud account. No credentials are committed.

## Versioning and limitations

`releases.lock.json` pins exact upstream commits. The initial projects repository has no published release, so the initial pair is explicitly labeled a pinned bootstrap snapshot. Later releases must pass compatibility and PDF/HTML checks before promotion.

The demonstration intentionally uses Psalm 23 with a WLC fallback. It cannot illustrate every project's annotations or source coverage, front matter or electronic behavior. Full builds preserve the selected settings without demo overrides.

All processor settings are editable; this hosted service accepts installed fonts and managed PNG/JPEG logos, not arbitrary filesystem paths, uploaded XML, remote assets or custom TeX.

## License

Application code: LGPL-3.0-or-later; see [LICENSE](LICENSE) and [COPYING](COPYING). Third-party notices are published at `/licenses` for the deployed bundle. Liturgical documents retain their individual TEI-declared licenses and generated colophons.
