# REM a22: independent AI founder and UI review

2026-10-03. An AI reviewer took the role of a technology founder with marketing
and UI experience. No human founder participated. The review used actual
rendered local pages on 1440 px desktop and 375 px phone viewports. Private
trial content and screenshots remain in the owner's protected REM trial area;
the images here use an invented notebook fixture.

## What was inspected

- An automatic eligible project page, including its first screen, full note,
  numbered Sources, source dialogs, and phone sticky header. The first trial
  attributed generic release requests to the project; a second trial was
  rendered and reviewed after the source rule changed.
- An explicitly requested private project page at desktop and phone widths,
  including its source dialogs, source hiding state, README claims, `Started`
  field, current finding and coverage note. The latest trial read 561 of 893
  matching archived inputs in its 730-day window.
- Two newly investigated person pages from a 730-day isolated map: the first
  screen, action banner, full memory, cited mail and coding-input dialogs, and
  Hide labelled passages state. The sampled pages' cited originals were
  available after the retained-input fix (6/6 and 8/8).
- The category sheet in default, filtered, hidden and scrolled states;
  record default, hidden, full memory and source-dialog states; and mobile
  Browse/search. Browser checks found no document or dialog horizontal
  overflow in the sampled states.
- The documentation site's local production build at `/rem`, `/releases`,
  `/releases/1.9.0a22` and `/cli/rem` on desktop and phone. These were reviewed
  locally before the package and documentation release.

## Findings and rechecks

| Priority | User impact and evidence | Change | Recheck |
| --- | --- | --- | --- |
| P1 | Automatic project v1 treated generic release requests from a shared working directory as project progress. A reader could infer the wrong current work. | Require a distinctive project, package, component, file, version or behavior match before using a session request. | Auto project v2 removed the generic release narrative; its first-screen mismatch is backed by repository and session sources. |
| P1 | One private project and one person page cited live coding inputs absent from the older mapped database. Their original-source dialogs could not open. | Retain only cited user inputs from an accepted investigation in the private state and resolve them in the reader. | Private project v4 opened all five cited originals; both sampled person pages opened all 6/6 and 8/8 cited originals, including the formerly missing input. Input-only scope remained visible. |
| P1 | Private project v5 cited `investigation:project-inventory` for file names. That item lists candidates rather than file contents and has no original-source dialog. | Writing guidance now forbids that citation; page validation rejects it and asks for a repository snapshot or an unresolved fact. | Unit validation rejects the inventory citation. The v5 trial remains a recorded failure for source completeness (7/8 openable), not a passing source audit. |
| P1 | Private project v5's `Now`, `Where it stands` and `Latest issues` added an event-driven listener question, while their cited live input asked only about a missed reply. The source does not support that mechanism. | Project writing rules now require reopening every cited original for current findings and dropping any mechanism, cause, status or action absent from it. | A separate, shorter isolated project trial must produce a current finding whose every clause is supported by its cited original; v5 itself fails this check. |
| P1 | A shorter private project v6 removed the unrelated missed-reply claim, but its `Try it` reversed the documented order of two core steps while citing the README. Readers could run the workflow incorrectly. | Require exact step order across `Overview` and `Try it`, with an original-source recheck; omit `Try it` when order is not established. | In a fresh trial, compare the rendered ordered steps with the cited README and verify no contradiction between the two sections. V6 is a failed instruction-accuracy sample. |
| P2 | The project hero led with a historical pattern while its useful current mismatch was below the first screen. The phone hero also clipped the useful text. | Prefer a supported `Now` finding and show the full project summary on phones. | Auto project v2 first fold shows the mismatch and decision on desktop and phone without clipping; fixture before/after images below show the structure change. |
| P2 | A grouped inline citation opened only its first member, and a 640-character repository excerpt ended before the cited hook signature. | Give every numbered Sources row its own 44 px target; show up to 16,384 characters of a retained repository source. | Sources 14, 16 and 17 opened individually. Source 17's dialog included the hook signature and required argument; source 14 included the release-policy paragraph. No dialog overflow at either width. |
| P2 | A person page's 1,026-character mail original had its explicit reply request beyond the old 640-character reader excerpt. | Show up to 4,096 characters of a cited mail body, marking truncation if longer. | Fresh desktop and phone render includes the reply request in the source dialog, with no overflow. |
| P2 | Hide labelled passages left an orphan period after a sensitive sentence in Full memory. | Include punctuation after a privacy marker and its citations inside the hidden span. | The fresh 375 px person page ends the visible relationship paragraph cleanly; the browser regression covers the marked sentence. |
| P2 | An old README could be read as current implementation, and first observed session date could be mislabelled as project start. | Require date or revision attribution for a repository snapshot and leave `Started` Unknown without direct evidence. | The next private trial kept `Started` Unknown; the independent rendered-page wording check is recorded below. |
| P2 | Private project v6 wrote `Last activity: Unknown`, but the reader called a mapped folder-session date “Last active” in its header and fact block. That overstates what the map proves. | Label the project census date “Last mapped session” in the header, fact block, side panel and sheet. | Reopen the fresh 375 px and desktop project views; the mapped date should keep its provenance and the authored `Last activity` should remain Unknown. |
| P3 | A partial project pass looked complete when its input window was not shown. | Show inputs read and available near the project status and on phone. | The explicit partial sample shows 561/893 for a 730-day window; the automatic four-input sample was complete for its queued inputs. |
| P1 | The first local documentation build linked the a22 review report to a file not yet included in that build, so the link returned 404. | Add the public report before the final production build. | Rebuild and open the report link from `/releases/1.9.0a22` on desktop and phone; expect HTTP 200. |
| P2 | The `/rem` expanded reference still sent readers to a20 notes, and `/cli/rem` called its source a published preview tag before a22 was published. The release note was hard to scan on a phone. | Link to a22's styled notes, use neutral preview-guide wording, and add short release-note headings. | Rebuild and inspect those exact pages and links on desktop and phone. |
| P2 | The `/releases/archive` Design Journal DD-053 link resolved under `/releases/` and returned 404. | Point it at the existing styled Design Journal route. | Open the link from the rendered archive; expect HTTP 200 and the intended decision article. |

## Public visual evidence

These screenshots use only `tests/fixtures/rem_reader_notebook.py` and invented
content. They show structure and interaction, not private trial claims.

| State | Evidence |
| --- | --- |
| Earlier desktop project | [before-project-desktop.png](before-project-desktop.png) |
| Earlier phone first fold | [before-project-phone.png](before-project-phone.png) |
| Current desktop project | [project-desktop.png](project-desktop.png) |
| Current phone first fold | [project-phone.png](project-phone.png) |
| Source dialog on phone | [source-dialog-phone.png](source-dialog-phone.png) |

## Limits and next recheck

The 730-day metadata-only trial completed in 989 seconds and mapped 382
people, 30 projects and 79 organisations. It left 326 people queued; two
sampled person pages do not establish the quality or affordability of the
remaining queue. The default mapping window stays 90 days. [Issue
#2176](https://github.com/openonion/connectonion/issues/2176) tracks resumable
history and the cost path.

The v5 private project is **not** a source-completeness or claim-accuracy pass:
its candidate file inventory citation and unsupported event-driven clause were
found after that trial. A future accepted project page must cite a retained
original for every new claim, and a reviewer should reopen every numbered
Sources row. This
review sampled relevant page types and states; it did not inspect every mapped
page, every provider thread or every screen in the application.

The shorter v6 trial read 138 of 893 archived inputs and removed the unrelated
missed-reply claim. It still reversed the source's workflow order in `Try it`
and used `investigation:page` for an old Paths bullet (5/6 openable sources).
It is another bounded failure sample, not a full-history quality pass.
A seven-day v7 candidate omitted the required `Open threads` heading and was
rejected without changing the notebook. It omitted the uncertain `Try it`
instead of reversing instructions and did not cite the candidate inventory or
old page. The project writer now explicitly retains `Open threads` as bare
`Unknown` when no current exchange is supported.

[Issue #2195](https://github.com/openonion/connectonion/issues/2195) tracks
the remaining claim-to-source accuracy check across fresh project trials.
