# REM morning memory visual review

## Scope and evidence

- Task: move the reader's first screen from processing statistics to remembered
  context, then give the owner a deliberate recall step.
- Build: `feat/rem-morning-memory` from `541a0486`; invented fixture notebook.
- State: latest pass changed a person, project, and organisation; an older person
  page supplies the recall answer. No private notebook data is in these images.
- Runner: Chrome via Playwright, 1440 × 900 desktop and 390 × 844 phone; light
  and dark themes; initial scroll position. Phone images are full-page.
- Before: [desktop](before-home-desktop.png), [phone](before-home-phone.png).
- After: [desktop light](home-desktop-light.png), [desktop dark](home-desktop-dark.png),
  [phone light](home-phone-light.png), [answer revealed](recall-revealed-desktop.png).
- Reference: [Attio record page documentation](https://attio.com/help/reference/managing-your-data/records/create-and-view-records),
  inspected 2026-10-01 for the relationship between context, activity, and next
  actions. It is a product behaviour reference, not a comparable screenshot.

## Comparison

| Question | Verdict | Visible evidence |
| --- | --- | --- |
| Did the intended effect carry across? | Partial | The first dark surface now leads with three current memories and an explicit link between two pages. Processing statistics are behind a disclosure. The brief still shows current page text, not a verified before/after change. |
| Is the relevant craft comparable? | Partial | First-screen hierarchy and phone thread layout are clearer. The library and detail pages retain the earlier notebook treatment, and the reader has no answer composer or action controls. |
| Largest remaining gap | 1. Evidence-backed questions; 2. durable recall state; 3. context-specific record pages | The user still cannot ask REM a question in this snapshot, and revealing a memory is not recorded. A person or project still opens as a long article. |

## Functional checks

- Passed: 20 browser tests across the changed home, reader navigation, empty
  state, search, review candidate safety, both themes, phone overflow, and
  keyboard menu; 25 related unit tests.
- Passed: the changed home at 1440 and 390 pixels had no document overflow;
  the recall button exposes its answer with `aria-expanded`, and the answer is
  hidden beforehand. Phone thread labels no longer overlap their text.
- Not tested: user retention over days, because the reader does not persist
  recall. No live source-backed answer or write action was added.
- The repository-wide `python -m pytest -q` run was stopped after 139 seconds
  during an unrelated network OIP test: 796 passed, 27 skipped, 248 deselected,
  with no failures reported before interruption. The complete suite is not a
  pass; the focused browser and unit checks above are the verification for
  this reader change.

## Independent design critique

Reviewer: AI, inspecting the before and after images above.

The first viewport now communicates REM's purpose more clearly: it presents
remembered context rather than the amount of work performed. The explicit
connection has a visible basis, and the recall card gives the owner something
to do with an older memory. The large dark card remains visually dominant;
on a notebook with only generic summaries, it can still feel like a decorated
catalog. A later preview should distinguish genuinely new findings from a page
that was merely rewritten. The detail pages and literal search remain the main
reason the product still feels like a Wiki.

Verdict: **revise** for the overall REM product; this homepage slice is ready
for preview review. The full project test suite is tracked separately from the
focused verification above.
