# Canonical navigation — candidate, 22 October 2026

Existing issue: #2197; related #2054 and #2060. Base main:
`e9bc54d1285d104715bcfa62b985f0f4cd5b8191`. Initial published/installed baseline was
1.9.3rc12; the 23 October follow-up uses installed 1.9.3rc16. This candidate is not released or visually accepted.

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
- Original-reference follow-up: incoming cards open an original-line passage panel;
  outgoing cards retain destination navigation plus a reference action. Repeated
  references use previous/next controls; opaque per-line IDs contain no prose and
  change when their source line changes. Removed IDs show an unavailable state.
  Mutual page references retain a separate incoming-location action without replacing
  the outgoing excerpt, citations or origin. Independent review found that original
  prose alone was insufficient: rendered chips and popup labels could still consult
  the displayed translation’s Sources. Explicit original-panel citation scope now
  covers both chip generation and popup/dropdown lookup; normal displayed scope is
  restored. A composed inline/chip/popup regression supplies conflicting source maps.
  The panel uses original text/citations even under cached translations, respects
  labelled privacy, and receives programmatic keyboard focus. Ref-bearing routes
  never alias to a different page. Code examples are excluded from links/mentions
  and the shared alias projection. This is a derived view, not another store.
- Read-only real inventory of 587 visible pages: 458 explicit forward connections,
  483 original-line locations, 25 connections with multiple locations. All page
  hashes unchanged. The inventory does not establish semantic truth or UI acceptance.
- Twelve new offline regressions cover per-line retention/removal, original-language
  citations, private-panel state, generated incoming/outgoing hrefs, focus/scroll
  dispatch, repeated controls, Windows line endings, code exclusion and aliases.
  Five initial regressions and one shared-alias privacy regression failed first.
  Related suites: 282 passed in 8.43s before the final whole-line popup test;
  all twelve follow-up contracts pass in 0.63s. Full final follow-up results pending
  in PR.
- Exact occurrence context is implemented as a passage panel, not direct scrolling
  to a rearranged summary. Current screenshots, phone layout, actual keyboard/focus
  and accessibility remain unverified. No native browser,
  renderer, screenshot workaround, real init/provider/model call or notebook write.
- The earlier dependency security blocker was superseded by maintainer changes
  published in rc13+; current main independently requires Python >=3.11. This
  navigation candidate still requires its own current-head CI/review and native
  acceptance. It has not been merged, tagged or published.

## Same-name identity follow-up, 23 October

The installed official rc16 reader selects the first exact title for a “related
to” query and the first title-containing record for Best match. A read-only title
census finds three same-title groups involving six eligible People pages; this
establishes ambiguity, not identity equivalence or a rendered misattribution.
Notebook hashes remained unchanged. Private identities and source IDs stay local.

Alternatives considered: merge same-name people (unsafe identity inference),
show only a warning (no actionable choice), or offer exact-record candidates.
The last option retains separate facts/connections, available original identifying
fields and privacy filtering. A unique related-name lookup remains direct; ambiguous
ordinary name searches suppress factual Best match and offer exact-page links.
Chosen relationship URLs retain the exact path and validate its eligibility and
name. A stale or held/service choice never falls back by name or merge alias.
Native links use descriptions associated with each candidate's fact list; an empty
list states that no visible identifying details are available.

Seven actual-search contracts failed first, with one unique-name control passing.
After repair, focused reader/identity suites pass 236 tests. Additional contracts
cover the real fact parser's original/translation cache boundary, privacy, unique
Best match and route dispatch. These run in Node with logical element stubs; they
do not verify rendered desktop/phone, tab order, focus or screen reader output.
No init, collection, model call, scheduled restart or real notebook write occurred.
Full integration and independent review results are recorded in the PR.

Independent AI review found one further integrity problem: the first chooser
dropped parsed qualifiers, turning a former company or dated role into an
unqualified hint. A real-parser regression failed for “(former)” and “(2019)”
before retaining each qualifier. Translation/cache and private-field controls
remain in the same regression. The first broad run was stopped for this correction;
its partial result is not final verification.
