# Changelog

## [Unreleased]

- Development follows the `main` branches of infra, opensiddur-processor and
  opensiddur-projects, redeployed on every merge to `main` and daily when any has moved.
  Production runs the latest Builder release with the newest full releases of
  opensiddur-processor and opensiddur-projects, found when it deploys; a new daily job
  redeploys it when either publishes a newer release, unless production updates are paused.
  Nothing upstream is pinned in this repository any more; production no longer builds from a
  bootstrap snapshot.
  Production deployments no longer wait for reviewers; only a first public launch does,
  on the new `prod-launch` environment, between the pilot and opening admissions.
- With opensiddur-processor v0.8.0, the Builder offers links to the scans and the electronic
  book's scan viewer: `typography.markers.scan_links` (where the link symbol goes:
  none, inline or margin), `typography.styles.scan_link`, and `electronic.scan_viewer`
  (opening a scan inside the HTML book, full screen, beside the text or below it). They show
  in full builds only: the preview's synthetic works have no scanned pages, and a preview runs
  no scripts and loads nothing remote. Full builds of the Birnbaum siddur, Asher's Selichoth
  and the 1822 Heidenheim Haggadah have links now; JPS 1917's come with the next
  opensiddur-projects book release, which production takes automatically. v0.8.0 also
  brings other export fixes, among them parallel PDF column flow, heading direction,
  note placement and character highlights; see its changelog.
- The worker image is built on Ubuntu 26.04 instead of Debian trixie, so PDFs are typeset
  with TeX Live 2025, as in the processor's CI and development. Under trixie's TeX Live 2024,
  parallel Hebrew–English columns swapped sides and their line numbers were set over the text
  (opensiddur-processor#338). Python 3.12 now comes from uv, since Ubuntu's is 3.14.
- Checks run ruff, the Python linter and formatter, on every push and pull request.
- The Builder lists the processor's typography roles for highlights, readings, foreign text,
  references, poetry lines and list items with the other styles.
- Pin the preview fixtures whose text is the name of the style that sets it, so a preview
  shows which setting changes what.

## [0.1.0]

- Launch the Open Siddur Builder with account sign-in, saved settings, source priorities, typography, and synthetic HTML and PDF previews.
- Build downloadable prayerbooks with the pinned Open Siddur processor and source corpus.
