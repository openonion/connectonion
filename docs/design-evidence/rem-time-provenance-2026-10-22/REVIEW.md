# Temporal provenance — candidate, 2026-10-22

Issue: #2629. Base: e9bc54d1285d104715bcfa62b985f0f4cd5b8191.
Installed/public preview checked this cycle: 1.9.3rc12. No release claim.

## Evidence and impact

Read-only saved notebook census: 587 Markdown pages. The initial metadata scan flagged two primary People candidates. Canonical
census recheck confirmed one maintenance-only activity projection; the other has
a source activity date and is excluded. The confirmed projection feeds a Last
contact label. Unknown-contact behavior is reproduced separately with an invented
fixture. This is a scoped static
finding, not semantic acceptance of all pages or a current rendered screenshot.
No private names, content, source IDs or local paths are included.

Before: offline regressions show a maintenance date returned as source activity,
and the latest-pass change list includes both an unrecorded recent footer and a
future-dated footer. Both tests failed against the unchanged base (2 failed,
220 deselected). After: source activity excludes maintenance; run membership comes
from recorded changed paths. The dated latest-pass/first-build summary works for
stale and midday runs, and missing claim history is described as missing recorded
changes rather than proof of no real-world change. Original maintenance footers
and map-derived contact fallback remain available.

## Alternatives and tradeoffs

File mtime is not activity: mapping can rewrite files. Date-only maintenance
footers do not identify the run that touched a page. A 24-hour cutoff does not
make daytime work overnight. Record evidence takes precedence over reassuring
freshness copy. Older runs lacking changed paths may show fewer attributed
rewrites; they do not acquire invented attribution. No notebook page is rewritten. A pass remains the rolling 18-hour run group.
First build means the first retained run group, not proof of the original init;
archived/deleted logs limit chronology.

## Verification and remaining acceptance

- Focused/related offline census, reader, design, model, people and service tests:
  **376 passed in 12.42s**. Initial additional timestamp test had a duplicate
  harness declaration, then assumed 24-hour formatting despite en-US locale;
  those test-only errors were corrected without changing production behavior.
- Read-only recheck: all **587 visible notebook page hashes unchanged**. An
  initial rglob included 2,416 hidden state Markdown snapshots; these are not
  extra notebook pages and are excluded from the coverage count.
- Full offline run and exact-head CI pending; no browser involved.
- Browser assertion strings are updated for future authorized native acceptance;
  updating them is not evidence of having run them.
- Independent AI source/product/copy review approved source d16c7b84 and
  inspected docs candidate; review did not include rendered/native acceptance.
- Current screenshots, desktop/phone layout, focus, contrast and screen-reader
  behavior remain pending. Preview access was previously denied; no alternative
  browser, HTTP/CDP/Playwright, CI screenshot or renderer workaround was used.
- No fresh real init, provider, mail, model or scheduled maintenance test.
- Python 3.10/Pillow security compatibility remains a release gate. No waiver,
  minimum-version change, merge, tag or publication is included.
