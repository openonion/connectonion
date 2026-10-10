# co rem rollout — independent AI role-based review

Review date: 2026-10-02. Reviewer role: technology founder with marketing and UI experience. This is an independent AI role-based review; no human founder participated. Production pages and rendered interaction states were inspected directly with Chromium/Playwright, with manual image review. No private notebook or real mailbox was read. O Chat reader flows use its deployed production UI with an intercepted scripted Host and invented Ada/Charles notebook.

## Coverage actually inspected

- `https://docs.connectonion.com/rem`: desktop 1440×900 and phone 390×844, hero, benefit explanation, sample disclosure, trust/limits section, preview install block, hero → “Try the preview” scroll anchor, and sidebar labels.
- `https://docs.connectonion.com/rem/demo`: desktop and phone, Today view, memory-change card, context reveal, “Open the page and source” → Mara page → highlighted cited source, header return/trial links, notebook privacy/sample disclosure.
- `https://docs.connectonion.com/cli/rem`: desktop and phone opening, preview banner, migration text, notebook root, navigation, initial workflow. Historical Wiki naming here refers to migration, not current branding.
- `https://docs.connectonion.com/cli/wiki`: navigated on both sizes and confirmed final canonical `/cli/rem`.
- `https://www.connectonion.com`: desktop and phone, hero/install CTA and identity/memory connection catalog. Current tile reads “co rem”; phone tile/spacing legible. Clicking the static catalog tile has no navigation; no claim made that it is an interactive link.
- `https://chat.openonion.ai/<synthetic-agent>/rem`: independently exercised phone Contents → Browse notebook → Search; parent production-run screenshots manually inspected for desktop/phone Ada page, offline and denied, plus desktop no-notebook. These explicitly name next steps and preserve privacy. Legacy and canonical selected-note fragments independently reproduced against production with the same synthetic Host.

SDK 1.9.0a19 was not public at the time of this initial review. Docs accurately advertised published 1.9.0a18 and stable 1.8.10. A post-publication recheck is pending.

## Significant findings

| Priority | Issue and user impact | Evidence / reproduction | Specific improvement | Recheck criterion |
|---|---|---|---|---|
| P2 | Demo still mixes standalone REM with co rem. The central product demonstration contradicts the current branding decision and teaches two names. | `/rem/demo` phone and desktop visibly show “What REM carried forward”, “REM / TODAY”, “REM / LATEST PASS”, “Remember with REM”, and “How REM processed the last pass”. Images `/tmp/rem-review-demo-viewport-phone.png`, `/tmp/rem-review-demo-viewport-desktop.png`, `/tmp/rem-review-reveal-desktop.png`. `public/rem/sample-reader.html` lines 1672, 1674, 1687, 1704, 1748 and other visible strings. | Change current visible demo labels and `connectonion/rem/reader.html` labels to co rem, or regenerate the sample from a corrected released reader. These strings are also present in the SDK19 reader source (1706, 1721, 1738, 1782, 1802–1803, 1842, 2097), so the issue extends beyond the frozen sample. Retain honest frozen/source-version disclosure; do not change JavaScript data object names or REM sleep explanation mechanically. | Production demo Today, reveal card and processing details use co rem consistently on both sizes; frozen/version labels describe the actual source. |
| P2 | Selected-note bookmarks open Contents, rather than the bookmarked note. The outer legacy redirect preserves the URL fragment, but the iframe never receives it. This affects canonical links too, so it is a reader issue, not a redirect failure. | Navigate synthetic Host to `/<agent>/rem#r=people/ada-lovelace.md` or `/<agent>/wiki?from=review#r=people/ada-lovelace.md`. Both retain outer `#r=...`, iframe `location.hash` is empty and visible heading is “What your assistant knows”. Independent script `/tmp/rem-independent-tests/review.spec.ts`; images `/tmp/rem-independent-shots/independent-canonical-fragment-inspection--canonical-fragment-contents.png` and `/tmp/rem-independent-shots/independent-legacy-fragment-inspection--legacy-fragment-contents.png`. Existing redirect test only checks that the Ada link is visible. | Safely seed the allowed reader fragment into the sandboxed document and assert selected note, query/fragment preservation and no frame reload / chat composer. | Both canonical and legacy selected-note links show Ada Lovelace heading as initial selected note, with query retained, no extra INPUT turn, and no frame-navigation warning. |
| P2 | Automatic GitHub-star popup blocks preview installation instructions on phone. It interrupts the primary trial path at the moment the user seeks the next command. | On `/rem`, click “Try the preview” and allow smooth scrolling to settle ~2 seconds. At 390×844 the automatic popup overlays the terminal commands. `/tmp/rem-review-start-settled-phone.png`. It is dismissible; this is obstruction, not a dead-end. | Suppress automatic promotion on co rem trial/demo pages, or postpone it until after exploration. Keep manual/footer promotion. | At 390px, hero → preview anchor leaves exact install/init/open commands unobstructed after the normal promotion trigger interval. |

Findings were sent to the release owner immediately. No reviewer changes were made to source branches or release pipeline.

## Lower-priority follow-up

P3: The CLI guide opens with “current branch contract”, an old update date and 1.8.8 preview/LTS planning before describing the user value and first workflow. The current-preview banner prevents a direct wrong-install problem, but the opening reads like development history and slows first-time comprehension. Keep migration/history further down and lead with current release availability and the init → open → start task. Evidence: `/tmp/rem-review-cli-top-phone.png`, `/tmp/rem-review-cli-top-desktop.png`. Recheck: first phone screen tells the current user what it does and how to begin without requiring interpretation of old issue/version references. This was not treated as a branding-release blocker.

## What worked in the inspected samples

- `/rem` clearly connects overnight maintenance to useful morning context; benefits, sample entry and preview entry are ordered sensibly.
- Opt-in alpha and ordinary stable installs are differentiated with an exact version pin. No unpublished 1.9.0a19 claim appeared in the inspected pages.
- Demo clearly says invented people/sources and frozen reader version. Changed fact versus rewritten prose, mapped versus investigated status, unknown fields, relationship basis and source citations are distinguished. Source2 link lands on and highlights the basis for the changed role.
- Context reveal expands on demand and points back to its notebook page. This supports progressive disclosure without claiming measured retention.
- Docs and sample have no document horizontal overflow at 1440px or 390px; source view iframe is also exactly 390px wide. Mobile typography and source list remain legible.
- Reader offline, denied and missing-notebook states use a clear heading, reason, exact next command and retry. Denied screenshot contains no notebook and describes owner-only access; the displayed browser address is a synthetic public address, not a private key.
- Canonical route and current public titles consistently use co rem outside the identified demo strings. Historical Wiki migration instructions remain contextual.

## Evidence and limits

Independent capture JSON: `/tmp/rem-review-pages.json`, `/tmp/rem-review-flows.json`, `/tmp/rem-review-source-flows.json`. Screenshots `/tmp/rem-review-*.png` and `/tmp/rem-independent-shots/`. Parent production reader screenshots were in `.worktrees/rem-branding-chat/e2e-screenshots/` and inspected visually, beyond its 12 passing acceptance tests.

This is sampled coverage, not an all-page pass. Not inspected: every SDK/CLI reference page, real private notebook content, actual mailbox initialization/model research, multi-provider scheduling or real Host identity enrollment, all theme combinations, screen-reader audit, keyboard-only full paths, all responsive breakpoints, remote relay failure/timeout/oversize/outdated states beyond the supplied screenshots, and GitHub README rendering/PyPI19 after publication. No change was inferred from a passing test alone.

## Post-release / fix recheck

Pending notification from release owner. This section will record actual rendered rechecks and any remaining gaps after fixes/publication.

### Local production-build fix recheck — 2026-10-02

Independent reviewer retained the same AI founder/marketing/UI role. No human founder participated. Fixes were inspected in actual local production builds, not inferred from source diffs or passing CI. SDK 1.9.0a19 is now publicly released per release-owner verification; SDK20 below is still a candidate and is not claimed published.

| Original finding | Fix inspected | Observed recheck result | Evidence |
|---|---|---|---|
| P2 standalone REM labels | Docs frozen sample now uses co rem for current labels; candidate SDK20 reader visible strings changed consistently. Frozen 1.9.0a13 dataset remains identified and desktop sample provenance explicitly says “current labels”. | Corrected Today title, latest-pass kicker, recall card and processing summary visually inspected on desktop/390px. Context reveal and source link remain functional. Existing typography/hierarchy and mobile stacking retained. | `/tmp/rem-recheck-demo-{desktop,phone}.png`, `/tmp/rem-recheck-reveal-{desktop,phone}.png`, `/tmp/rem-recheck-sdk-after-{desktop,phone}.png`, `/tmp/rem-recheck-sdk-reveal-{desktop,phone}.png`. Four release images `docs/releases/assets/v1.9.0a20/{before,after}-{desktop,phone}.png` were separately viewed. |
| P2 selected-note bookmarks | Local production O Chat `http://127.0.0.1:3111` passes initial note selection through to opaque iframe. | Canonical `/rem?from=independent#r=people/ada-lovelace.md` and legacy `/wiki?from=independent#r=people/ada-lovelace.md` both visibly open Ada on desktop and phone. Outer canonical URL/query/fragment retained, sandbox remains opaque (`window.origin === 'null'`, no `allow-same-origin`), no `INPUT`, no chat composer, no frame-navigation warning. Offline and denied remain clear and carry no iframe. Eight independently written checks passed; key bookmark screenshots manually inspected. | `/tmp/rem-recheck-tests/review.spec.ts`, `/tmp/rem-independent-recheck-shots/rem-bookmark-opens-ada-desktop--ada-bookmark-rem-desktop.png`, `/tmp/rem-independent-recheck-shots/wiki-bookmark-opens-ada-phone--ada-bookmark-wiki-phone.png`. |
| P2 GitHub promotion overlays trial | Local docs `http://127.0.0.1:3112` suppresses automatic promotion on `/rem` and its child routes. | Hero → trial anchor settled with start section at ~96px; zero “Star us on GitHub” popups; exact public SDK19 install/init/open/start commands unobstructed on desktop and phone. | `/tmp/rem-recheck-start-{desktop,phone}.png`, `/tmp/rem-recheck-data.json`. |

Additional observed rechecks: docs demo reveal changes to “Hide the context” and displays the remembered answer; “Open the page and source” opens Mara and highlights source2 on both sizes. Candidate real SDK20 `file:///tmp/rem-a20-pages/after.html` independently renders the same fictional notebook and retains reveal plus source2 navigation. Source2 wording matches the original fictional evidence. Source views remain 1440px/390px wide with no horizontal document overflow. Before and after candidate HTML were both rendered so this review compares actual presentation. No P0/P1 issue or new significant regression was found in these sampled rechecks.

The three P2 findings are **verified fixed in the inspected local builds/candidate HTML**, awaiting deployed-production recheck. The P3 guide-opening follow-up remains open and does not block this copy/URL correction. Original coverage gaps still apply; production O Chat and docs deployment, PyPI20 artifact and final README/release rendering were not yet independently inspected during this local round. The immutable SDK19 release was not altered by these fixes.
