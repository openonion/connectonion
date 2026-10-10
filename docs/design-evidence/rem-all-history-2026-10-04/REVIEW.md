# Historical contacts in the REM reader

## Scope and evidence

- Intended action: find a correspondent from older mail without treating a single header as a verified person memory; prepare a page only after review.
- Baseline: published `v1.9.0a39` (`c49ddfe1`); candidate: `feat/rem-all-history-people-2176` on the a39 reader, rebased for PR. Both screenshots use the invented `tests/fixtures/rem_reader_notebook.py` data. No real contact is exported.
- Browser: headless Chrome, 100% zoom; 390 × 844 phone and 1440 × 1000 desktop; full-page screenshots in light and dark. The opened directory and command row are explicit states. The top viewport and page scroll length differ because the new content exists only in the candidate.
- Before: [phone](before-people-light-phone.png), [desktop](before-people-light-desktop.png).
- After: [collapsed phone](after-people-light-phone.png), [open phone](after-contacts-light-phone.png), [dark phone](after-contacts-dark-phone.png), [desktop](after-contacts-light-desktop.png), [command under selected contact](after-contact-command-light-phone.png).
- Capture command: `python scripts/capture_rem_reader.py OUT_DIR --only people --only contacts --only contact-command` with the repository's installed Chrome/Playwright runner. The baseline uses the a39 script and fixture.
- Reference: the prior REM People view is the direct product baseline. No external product screenshot was used to infer interaction quality.

| Question | Verdict | Visible evidence |
| --- | --- | --- |
| Did this surface make historical contacts findable? | Reached for observed mail | Baseline ends at the main People sheet; candidate adds a separate, searchable directory with three invented old contacts and an explicit coverage statement. |
| Is the relevant craft comparable to the existing reader? | Reached in this state | Desktop keeps the main table and gives the secondary directory a quiet fold. Phone uses readable cards, full-width search, aligned dates and mail counts, and a 44px action. Light and dark use existing reader tokens. |
| Where is the largest gap? | Follow-up | Preparing a contact still hands off to the CLI; it does not complete from the reader. The main People sheet also remains a horizontally scrolling table on phone. Neither this directory nor a metadata scan proves a mature memory experience. |

## Functional checks

- The unit and CLI subset passed 356 tests after the first integration; the latest focused init subset passed 151 tests. The opt-in reader browser suite passed 55 tests; the directory and phone checks passed again after the card layout and inline command change.
- Search filters by name or email. The command appears directly after the selected contact, is shell quoted, and can be copied. A one-off address produces no empty Markdown page.
- Browser checks covered a 390px phone with no document overflow, the directory's named search field, the command's adjacency, and a 44px mobile action. The 375px mobile suite covered both themes, focus and keyboard behavior on representative reader controls, privacy mode, reduced motion, and source dialogs.
- A separate 64-character Skill source ID made the previous mobile citation tooltip extend the document by 106px. The mobile tooltip now stays within the viewport; the Skill evidence test passes.
- Real metadata-only census was run privately. Outlook scanned 18,737 headers; Gmail's account-address read timed out. Counts shown in issue #2176 are a lower bound and none of the real data appears in these screenshots.

## Independent design critique

- Reviewer: Codex AI, inspecting the images named above at their actual phone and desktop widths.
- Initial phone attempt used a five-column table. It technically fit but broke addresses and action labels into character-by-character lines; design verdict: **revise**.
- Revised phone view uses cards and a command row next to the chosen contact. It has readable identity, date and count hierarchy, a clear button, and no sideways scroll; verdict: **pass for this secondary directory**.
- Remaining product issues: CLI handoff is still required to create the page; the Outlook-only scan cannot claim all connected history; the main People sheet is still dense at 390px. Product maturity remains **pending**.

| Iteration | Criticism | Change | New screenshot | Verdict |
| --- | --- | --- | --- | --- |
| Initial | Five columns turned addresses and buttons into vertical letter stacks on phone. | Replaced the phone table layout with cards. | `after-contacts-light-phone.png` | Pass for readable directory. |
| Follow-up | The revealed command appeared below the whole directory and was hard to select. | Moved it under the chosen contact and added Copy command. | `after-contact-command-light-phone.png` | Pass for the CLI handoff state. |

## Final status

- Functional verification: pass for the mapped-contact directory and background-start integration; full private Gmail coverage is unresolved.
- Baseline comparison: reached for discoverability and phone readability.
- Independent visual review: pass for the named directory states; whole-product review remains open in #2065.
