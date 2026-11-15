# Changelog

## [Unreleased]

- The worker image is built on Ubuntu 26.04 instead of Debian trixie, so PDFs are typeset
  with TeX Live 2025, as in the processor's CI and development. Under trixie's TeX Live 2024,
  parallel Hebrew–English columns swapped sides and their line numbers were set over the text
  (opensiddur-processor#338). Python 3.12 now comes from uv, since Ubuntu's is 3.14.
- Checks run ruff, the Python linter and formatter, on every push and pull request.
- Development follows the newest release *or prerelease* of opensiddur-processor and
  opensiddur-projects, and the latest infra `main`: every development deployment that is
  not a release finds them, and development is redeployed on every merge to `main` and daily
  when any has moved.
  Production still builds only from `releases.lock.json`, which a check (on every pull
  request, and before a release deploys) now requires to pin full releases, named by tag.
- Pin opensiddur-processor v0.8.0, with links to the scans and the electronic book's scan
  viewer. The Builder now offers `typography.markers.scan_links` (where the link symbol goes:
  none, inline or margin), `typography.styles.scan_link`, and `electronic.scan_viewer`
  (opening a scan inside the HTML book, full screen, beside the text or below it). They show
  in full builds only: the preview's synthetic works have no scanned pages, and a preview runs
  no scripts and loads nothing remote. The opensiddur-projects pin stays at v20261108; JPS
  1917's links to its scan come with the next book release.
- Pin the first published releases: opensiddur-processor v0.7.0 and the opensiddur-projects
  book release v20261108. The pins are no longer a bootstrap snapshot.
- Pin opensiddur-processor with the typography roles for highlights, readings, foreign text,
  references, poetry lines and list items, so the Builder lists them with the other styles.
- Pin the preview fixtures whose text is the name of the style that sets it, so a preview
  shows which setting changes what.

## [0.1.0]

- Launch the Open Siddur Builder with account sign-in, saved settings, source priorities, typography, and synthetic HTML and PDF previews.
- Build downloadable prayerbooks with the pinned Open Siddur processor and source corpus.
