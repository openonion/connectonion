# REM first-run project count — preview evidence

## Scope and evidence

- Task: keep the first-run Projects directory consistent with the map the owner just saw.
- Build: candidate based on `v1.9.0a14` (`1465a2b9`), with `project_material.extract(create_pages=False)` used only by `init`.
- State: an invented notebook maps Alpha. A later session scan finds messages in Alpha and in an unmapped Beta folder. The before state uses the 1.9.0a14 default page-creation path; the after state uses the new init path. No private notebook content appears here.
- Runner: Chrome headless, light theme, 100% zoom, top of Projects, 1440 × 900 and 390 × 844. Screenshots show the whole document.
- Before: [desktop](before-desktop.png), [phone](before-phone.png). After: [desktop](after-desktop.png), [phone](after-phone.png).
- Reference: the before state is the behavior under review, captured from the same invented source material. This is a data-integrity comparison, not a comparison with another product's visual style.
- Limit: the fixture has only two projects and no investigated project content. An installed-wheel private five-day init separately reported 3 mapped projects and 3 final project files, with 0 material-created pages; no private page or screenshot is published.

## Comparison

| Question | Verdict | Visible evidence |
| --- | --- | --- |
| Did we achieve the intended effect? | Reached in the fixture | Before lists Alpha and the silently added Beta, `0 written of 2`; after lists only mapped Alpha, `0 written of 1`. |
| Is the relevant craft comparable? | Partial | The count, filter and row agree with the map after the change at both widths. The table is still a compact catalog, not the finished product experience. |
| Where is the largest gap? | Unmapped candidate review, then richer project state | Beta remains a private candidate in `.state/projects/index.json`; the reader has no review flow for it. A mapped project's value still depends on investigation. |

## Functional and visual checks

- The synthetic before and after documents had no document-level horizontal overflow at either viewport (scroll width equaled viewport width).
- The Projects category opened directly in Chrome at both widths; no model, network source or approval flow was involved in this comparison.
- Keyboard order, screen-reader output, dark mode and long populated project pages were not retested because this change does not modify reader controls or layout. Existing reader browser coverage remains the relevant gate for those behaviors.
- Independent AI visual review: **pass for count consistency in these states; pending for overall product design**. On phone, the count and two rows are visible without vertical search, but the table still requires horizontal scrolling for later columns.

## Final status

Functional regression: focused test passes. Reference comparison: reached for the project count. Visual review: pass for this narrow change. The full REM maturity bar still requires an owner-reviewed real first run, trusted nightly changes, correction, retrieval and recall across several days.
