# Changelog

## [Unreleased]

- Pin opensiddur-processor with links to the scans and the electronic book's scan viewer. The
  Builder now offers `typography.markers.scan_links` (where the link symbol goes: none,
  inline or margin), `styles.scan_link`, and `electronic.scan_viewer` (opening a scan inside
  the HTML book, full screen, beside the text or below it). They show in full builds only:
  the preview's synthetic works have no scanned pages, and a preview runs no scripts and loads
  nothing remote. Pin opensiddur-projects with the JPS 1917 page breaks linked to its scan.
- Pin the first published releases: opensiddur-processor v0.7.0 and the opensiddur-projects
  book release v20261108. The pins are no longer a bootstrap snapshot.
- Pin opensiddur-processor with the typography roles for highlights, readings, foreign text,
  references, poetry lines and list items, so the Builder lists them with the other styles.
- Pin the preview fixtures whose text is the name of the style that sets it, so a preview
  shows which setting changes what.

## [0.1.0]

- Launch the Open Siddur Builder with account sign-in, saved settings, source priorities, typography, and synthetic HTML and PDF previews.
- Build downloadable prayerbooks with the pinned Open Siddur processor and source corpus.
