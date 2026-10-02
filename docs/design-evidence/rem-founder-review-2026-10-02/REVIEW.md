# Independent REM experience review — 2026-10-02

An independent AI reviewer used the perspective of a technology founder with
marketing and UI experience. This was a role-based review, not participation by
a human founder. The review inspected rendered structure, content and design,
then rechecked the fixes. Private notebook screenshots and source text remain
outside this repository.

## Coverage and evidence

- Before/after captures: home, owner, person, project, organization, skill and
  mapped person at 1440×1000, 375×812 and 768×1024. Each capture set has 21
  screenshots, zero JavaScript errors, zero external requests and zero page
  overflow. The reviewer inspected all 21 initial screenshots, eight selected
  final-after screenshots and all eight real interaction screenshots.
- Eight real notebook interaction states: phone context expansion, full sources,
  source dialog, mapped command copying, navigation, search match, search with
  no match, and a dark skill page. Expansion/collapse and navigation Escape were
  exercised; the copied command matched the browser clipboard and included the
  displayed notebook root. No paid investigation was executed by this check.
- A synthetic archived excerpt was visible before hiding and remained visible
  under the old privacy behavior. After the fix it is hidden with an explanation.
  This proves the UI behavior with invented material, not an observed disclosure
  of a particular private message. The first wrong-key fixture had no archived
  body and was discarded as invalid evidence.
- Current checks: **14 browser tests passed in 37.48 seconds**, including phone
  light/dark layouts; **34 focused unit tests passed in 1.96 seconds**.
  Intermediate test failures from stale selectors, formatted dates and invalid
  synthetic fixtures were corrected before this gate.

## Findings fixed in this draft

| Priority | Problem and user impact | Change | Recheck |
| --- | --- | --- | --- |
| P1 | Short conclusions could be clipped on phones without a way to read them | Show expansion based on rendered overflow; use a 44px button | Expand/collapse a conclusion under 180 characters; resize to desktop |
| P1 | The copied investigation command could target the default notebook | Include the snapshot's explicit root | Compare generated command with clipboard and displayed root |
| P1 | A stale index could contradict the page's last-contact date | Use the census date in the summary facts | Inject a conflicting index date; compare summary and full fact card |
| P1 | Unassigned checks were counted as waiting on other people | Separate them into Other open context | Neutral rows do not appear in Waiting on others |
| P1 | Organization and skill leads did not answer their headings | Prefer existing Our relationship and When to use sections; add a sources entry | Reinspect both types and exercise sources navigation |
| P1 | Hidden mode left original source and conversation excerpts visible | Withhold unclassified descriptions/excerpts in that mode; preserve labelled private spans in promoted summaries | Toggle while dialogs are open; show again and recover the original excerpt |
| P2 | No recorded skill invocation was presented as no use | Say recorded invocations / no invocation found | Reinspect a zero-invocation skill |

## Remaining improvements

Tracked in #2065; these remain open rather than being described as fixed:

- **P2, mobile hierarchy:** repeated action/date metadata pushes the mapped
  investigation CTA below the first viewport. Recheck at 375px with a clear
  state and next-step entry visible without long scrolling.
- **P2, relationship clarity:** some connected-context explanations are slugs or
  index headings. Put supported relationship explanations first and distinguish
  navigation links from evidence of a relationship. Recheck the first displayed
  connections on owner, person and mapped pages.
- **P2, process state:** a populated initialized notebook still says sources have
  not been authorized when background passes are off. Distinguish initialization
  from background scheduling and recheck both states.
- **P2, skill semantics:** Last active can refer to investigation, while recorded
  invocation counts do not establish successful outputs. Keep those meanings
  clear; do not present investigation status as behavioral verification.

The broader custom-root refresh/path-copy concerns in #2146 are still open;
this round fixes investigation command generation only.

## Limits

This is sampled experience coverage, not an all-record accuracy pass. It does
not validate every generated clause against its original source, every page or
all empty/long/conflicting notebook states. The source dialog deliberately says
its excerpt is original context, not a validated claim span. The current draft
does not publish a package, bump a version or enable background processing.
The sampled real source dialog had no archived body, so opening its citation
did not establish support for the claim.

## Ongoing review rule

After each completed update round, release or trial, obtain an independent
review of relevant rendered page types and interaction states. Record priority,
user impact, evidence and concrete recheck criteria. Fix significant issues in
the authorized scope and inspect the result again. State actual coverage and
remaining gaps. This rule is recorded in `AGENTS.md`.
