# REM owner first-run review, candidate after 1.9.0a19

## Scope and evidence

- Task: keep a recent, consequential owner decision in the first-run evidence packet; remove a person-only empty section and an unrelated contact date from the owner page.
- Build: `feat/rem-owner-schema-a19` rebased onto main merge `91b32942` (the 1.9.0a20 reader-label candidate). These are candidate screenshots, not an installed release.
- State: invented Avery / Harbour notebook. The before state adds the two defects seen in a private 1.9.0a18 owner page; the after state applies this branch's deterministic cleanup. Both use the same candidate reader and content otherwise.
- Capture: `python scripts/capture_rem_owner_schema.py docs/design-evidence/rem-owner-schema-2026-10-02` in a venv with Playwright and Chrome. Chrome, light theme, 100% zoom, 1440×900 / 900×900 / 390×844; keyboard opens the full note. No network requests.
- Source: invented fixture in `tests/fixtures/rem_reader_notebook.py`, captured locally on 2026-10-02. Private notebook text and screenshots are not included.

| Width | Before | After | Visible result |
| --- | --- | --- | --- |
| 1440 | [expanded desktop](before-desktop-expanded.png) | [expanded desktop](after-desktop-expanded.png) | The old note's contact-date tail and empty-field notice are gone. |
| 900 | [expanded intermediate](before-intermediate-expanded.png) | [expanded intermediate](after-intermediate-expanded.png) | The same content order holds at intermediate width. |
| 390 | [expanded phone](before-phone-expanded.png) | [expanded phone](after-phone-expanded.png) | The note no longer ends with “1 section still to learn” for a field that does not belong to the owner. |

[After, phone first viewport](after-phone-top.png) shows the cited change and next step without opening the note.

## Three comparison answers

| Question | Verdict | Evidence |
| --- | --- | --- |
| Did the intended effect land? | Partial | The empty field and unrelated date disappear in the expanded note; a source-backed change remains in the first viewport. A real 14-day init still hit a citation failure. |
| Is the craft comparable to a mature memory product? | Unknown | No live reference is comparable to this private-first-run state. The current reader has a useful decision hero and links, but the expanded phone note remains long. |
| Largest gap? | First-run reliability, then focus | The longer real run could not promote a cited candidate. In the successful run, unrelated obligations still competed with the main decision. |

## Private first-run checks

An isolated five-day candidate init completed with zero reported errors. Its owner page cited the earlier and later init choices in the lead, had 11 headings, four `Unknown` values, six internal links, and 15 listed sources. The irrelevant person-only heading did not recur. Its lead still included a last-contact sentence and two unrelated `At stake` bullets; those findings led to the later deterministic lead cleanup and shorter focus rule.

A separate isolated 14-day init failed owner promotion on an unidentifiable citation, before an owner page could be accepted. This is a real first-run failure, not a visual defect. The existing init-coverage PR #2141 includes a bounded citation-repair path but is not merged. Neither run proves reliable first-run quality across source mixes. Source text, IDs, names, and private screenshots are withheld.

A third isolated five-day init, after tightening the owner writing rules, also failed at the quick owner pass on an unidentifiable citation. Its source collection reported no errors. This raises the citation-repair path above further wording changes; a better prompt alone has not made first init reliable.

## Functional and design review

- Functional: the synthetic owner page opened at all three actual viewport widths without horizontal overflow. Keyboard focus and Enter opened `Full memory and sources`. The page had no browser errors or network requests. Unit checks cover section removal, substantive-section rejection, preserved citations, and the decision packet.
- Visual critique (AI, inspected the phone before and after images): removing the meaningless section notice makes the note end cleanly. The hero is more useful than a generic article lead. The Facts block still dominates the expanded phone page, and the primary memory lacks a direct correction action. This candidate improves the named owner defects but does not pass the product maturity bar in `rem-product-audit-2026-10-01.md`.
- Remaining journey checks: installed-wheel reruns across source mixes, night-to-morning change proof, correction, retrieval, and recall over days on phone and desktop.
