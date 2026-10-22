# Canonical navigation — candidate, 22 October 2026

Existing issue: #2197; related #2054 and #2060. Base main:
`e9bc54d1285d104715bcfa62b985f0f4cd5b8191`. Published/installed preview remains
1.9.3rc12. This candidate is not released or visually accepted.

## Evidence and correction

A fresh read-only inventory of 587 visible notebook pages finds four relative
Markdown references without a target in the notebook and zero fragment references.
All 587 page hashes are unchanged. This is structural evidence, not all-page
semantic or visual acceptance. No private identities, excerpts, paths or source
IDs are published here.

The initial description that missing links all became plain text was too broad:
body links already had a dead-link style, with a malformed literal `title=t(...)`
attribute. Related links retained only their labels. The candidate keeps a valid,
escaped translated explanation and visible “Page unavailable” text on both surfaces.
It does not assert that a missing page was deleted or that its raw source is gone.

## Chosen design and authority

Use the existing merge table to derive validated redirects to existing records;
reject loops, malformed values, root escapes, hidden/archive paths and overrides
of a live record. Local readers may use valid redirects for bookmarks. Shared
snapshots include only old keys explicitly referenced in current exported Markdown,
flatten chains and omit reasons, archive metadata and unreferenced history.

Normalize relative page URLs consistently in Python and JavaScript: split fragments
before decoding, decode once, reject malformed escapes/root traversal, and preserve
valid heading targets. Use the same projected redirects for explicit links and
backlinks. Original labels, excerpt origin, privacy flags and source numbers remain
attached to the originating page. No second relationship store or identity inference
is introduced, and no notebook links or source pages are rewritten.

A review of the first implementation exposed an authority error: globally aliasing
`byPath` could bind an old run's claim/source numbers to a different merged page.
The final design keeps exact data lookup and uses a separate navigation resolver.
Old numbered-source anchors are not redirected without a source-number mapping
ledger. Ordinary page/section bookmarks keep heading and filter state. Source popup
lookups remain exact. A navigation redirect is not proof of identity or evidence.

## Verification and limits

- Five baseline canonical/encoded/backlink/snapshot regressions failed.
- Independent review found encoded `.md` extensions losing missing status: two
  English/Chinese body+Related regressions failed before unifying classification.
- Two further regressions exposed global claim lookup rebinding and uncanonicalized
  route state; a model regression also exposed rebinding an old numbered-source link.
- Initial related suites passed 266 tests; the first implementation's full offline
  run passed 16,990 tests with 334 skips. That result predates the provenance
  correction and is not final acceptance. Final related/full results follow in PR.
- Boundary contracts cover malformed/encoded paths, exact path authority, cycle
  rejection, shared history minimization, translation/escaping, source popup lookup,
  source anchors and removal of backlinks after a reference is removed.
- Cached translated snippet lookup still uses its previous URL matcher; encoded or
  aliased links can truthfully fall back to the marked original excerpt. Language
  completeness remains #2060. Separate snippet-provenance PR #2625 is not included.
- Backlink scrolling to the exact originating mention, current screenshots, phone
  layout, keyboard/focus and accessibility remain unverified. No native browser,
  renderer, screenshot workaround, real init/provider/model call or notebook write.
- Dependency security/compatibility gates still block publication; no advisory waiver,
  Python minimum change, merge, tag or package availability claim is included.
