# REM owner-page first-run review, 1.9.0a18 candidate

The goal is a first-run memory the owner can act on: an evidenced change of
decision, the consequence, and a path into the work. This review covers the
owner page. It does not establish REM's night-to-morning, correction, recall,
or multi-day quality gates.

## Private first-run evidence

The published 1.9.0a17 package installed in an isolated environment and ran a
five-day first init against the owner's local sources. Its owner lead remained
a broad quality request, and an unrelated optional mail item rose near the
top. Candidate iterations exposed two separate failures: the full writer
could miss an earlier decision already cited by its quick pass, and a valid
fact citation from unsampled mail could fail source identification. The latter
stopped one init before page promotion.

After the fixes, a fresh isolated five-day init completed the owner quick and
full passes with zero reported errors. The final owner page led with an
earlier-to-later change in the first-run approach, citing both original coding
messages; it kept the requested outcome unverified. It had three cited Insight
bullets, 17 listed sources, six internal links and four `Unknown` values. This
is one private run, not a measured success rate. The source text, identifiers,
names and screenshots from that private notebook are not published.

The remaining real-page weakness is a low-value miscellaneous history item and
a broad next-step sentence. [#2008](https://github.com/openonion/connectonion/issues/2008)
continues to track owner history, identity, correction and recall quality;
[#2128](https://github.com/openonion/connectonion/issues/2128) records this
focused first-run slice. The relationship links are only the first exact,
cited owner-to-project path under
[#2060](https://github.com/openonion/connectonion/issues/2060).

## Visual check with invented data

All images below use the invented notebook fixture and are reproducible with
`python scripts/capture_rem_owner_aha.py docs/design-evidence/rem-owner-aha-a18`.
The script checks horizontal overflow at 1440, 900 and 390 px. At phone width
it focuses the project relation, activates it with Enter, and checks that the
project page opens. Both states use the candidate reader. The before state
keeps the fixture's prior generic owner note; the after state adds an invented
cited change. This isolates content hierarchy, not an exact a17 pixel diff.

| Width | Before | After | Observation |
| --- | --- | --- | --- |
| 1440 px | [desktop](before-desktop.png) | [desktop](after-desktop.png) | Change and next step lead without losing sources. |
| 900 px | [intermediate](before-intermediate.png) | [intermediate](after-intermediate.png) | Hierarchy survives the intermediate layout. |
| 390 px | [phone](before-phone.png) | [phone](after-phone.png) | Change, next step and linked project fit in the first screen; no horizontal overflow. |

The [phone destination](after-project-phone.png) confirms keyboard navigation.
The project page's own hero still truncates context on a narrow phone. This
remains reader work under
[#2065](https://github.com/openonion/connectonion/issues/2065).

## Verification limits

Unit tests cover temporal packet selection, fact-source validation, bounded
owner-to-project links and the reader hierarchy. The fresh real run verifies
that both owner passes complete and the final page cites original sources.
It does not verify nightly scheduling, morning recall, repeated-day usefulness
or that every owner will have a meaningful reversal in the source window.
