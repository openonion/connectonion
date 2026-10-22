# Quotation boundaries — candidate, 22 October 2026

Issue #2635; related closed #2471 quotation formats and #2233 attribution.
Base main e9bc54d1285d104715bcfa62b985f0f4cd5b8191. Newest installed/public
preview remains 1.9.3rc12. No release/native/model acceptance claimed.

## Source failure and correction

`_plain` removes every whitespace character; quote matching then looks for a
substring. It accepted synthetic `now here`/`nowhere` and `notable`/`not able`
word changes. It can also find a fragment inside a larger word. Initial strict
regressions: four failures, 35 passes. Quotation-specific normalization now keeps
word separation; unrelated global claim-key matching remains unchanged.

The first strict candidate passed 39 tests but newly rejected two real valid
quotations next to flattened legacy headings/mail headers. Private source
inspection confirmed that failure; it was not proof the saved quotes were wrong.
The final design rejects changed internal wording but treats ambiguous outer
edges as structured unresolved evidence. No arbitrary camel-case separator rule,
archive migration or real note rewrite is used.

## Final design

- English/Korean word spaces remain significant. Tested Han/kana intercharacter
  wrapping is normalized with a narrow policy; Hangul is excluded. Punctuation
  spacing is matched flexibly while retained source separators remain intact.
- Only complete available cited originals enter determinate checks. Ellipsis
  fragments remain ordered; missing/truncated sources stay unjudged.
- Boundary warnings carry the quote, its numbered references, matching cited source
  IDs and at most 640 retained characters around the first fragment. No raw span
  found is explicit; the excerpt is not MIME or a segmentation verdict. No unrelated
  source material or guessed text enters the warning.
- The actual bounded source audit receives warnings and originals. Audit records
  persist them; a global PASS with unresolved boundaries becomes INSUFFICIENT.
  The existing non-refusal policy for insufficient evidence remains unchanged.
- Without an auditor, promotion review still records diagnostics and unassessed,
  unresolved factual quality. This does not classify the quote as verified.

## Evidence and limits

- Four-suite related quote/source-audit/page-review/runner regression: **462 passed
  in 8.68s**. Tests exercise actual audit dispatch, conflicting word/negation and
  compound edges, legacy flattened controls, bounded cited contexts, no-auditor
  records and global-PASS handling. First full run: two session-summary regressions
  failed, 16,989 passed, 334 skipped in 157.41s. Global caller search then found two
  native-session paths still passing whitespace-erased source text. Both now use
  spacing-preserving original input and whole-word checking, including saved-summary
  display. Raw attachments and exact message/time binding remain covered. After
  this production correction, five related suites pass **611 tests in 9.70s**;
  the final fresh full result follows in the PR.
- Read-only inventory: 587 visible pages, 49 with checked-style quotes, 122 cited
  quotations; 63 had complete available originals and 59 did not. Final classifier
  reports two preexisting literal mismatches and two legacy-layout boundary warnings.
  The two preexisting mismatches were inspected against their retained cited texts;
  this is not an audit of every paraphrase, attribution or source identity.
- All 587 visible page hashes unchanged. Private passages, identities, paths and
  source IDs remain private; public examples are invented/deidentified.
- Independent source review found and resolved the overly strict legacy behavior,
  Hangul spacing policy and diagnostic persistence/generic-PASS concerns. Exact-head
  confirmation, full CI, real model efficacy, current desktop/phone/source dialogs,
  keyboard/accessibility and overall maturity remain separate gates.
- No actual init/provider/model/scheduler call, auth/restart, browser/renderer
  workaround, version bump, merge, tag or publication. Security/compatibility gates
  remain in force; no advisory waiver or Python minimum change.
