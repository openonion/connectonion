# REM connected reader — 1.9.0a13 visual review

This review uses the invented notebook in `tests/fixtures/rem_reader_notebook.py` for publishable screenshots. It was captured in Chrome at 1440 × 900 and 390 × 844. The browser loaded the generated `file://` reader with no network requests or page errors. All tested views fit the viewport width.

| Task | Desktop | Phone | Result |
|---|---|---|---|
| Return to today's context and obligations | [Today](today-desktop.png) | [Today](today-phone.png), [dark](today-phone-dark.png) | Current context, recall, open threads, and category entry points are visible; run mechanics stay in a disclosure. |
| Resume a relationship | [Person](person-desktop.png) | [Person](person-phone.png), [dark](person-phone-dark.png) | State, next exchanges, compact facts, connections, cited conversation, and dated activity precede the original note. |
| Resume a project | [Project](project-desktop.png) | [Project](project-phone.png) | State, next exchanges, purpose, a decision, linked people and organisation are navigable. |
| Tell a claim change from a page rewrite | [Memory changes](changes-desktop.png) | — | A cited field value change is shown separately from rewritten pages. |
| Find what needs action | [Open threads](open-threads-desktop.png) | — | All supported open loops have a direct record link. |
| Inspect provenance | [Original source](source-desktop.png) | — | A citation opens an archived excerpt and names the generated source description separately. |
| Read a cited conversation | [Conversation](conversation-desktop.png) | — | Messages are in time order; the view states the archived total and visible count. |

The same views were checked in dark mode at 390 px in browser tests. The eye trace mark is legible at rail and phone sizes; labels, focus and reduced-motion handling do not rely on its colour or motion.

## Private real-notebook acceptance

The owner explicitly authorized local testing with their real REM notebook. Ten before and ten after screenshots were captured in a private temporary directory and inspected locally. They are not part of this repository or PR. On the same records, desktop height changed from 9,083 to 1,855 px for the person page and 11,300 to under 2,000 px for the project page. At 390 px, the person page changed from 14,507 to 3,051 px. The new pages had no document-level horizontal overflow or JavaScript errors. The homepage changed from 3,898 to 2,679 px on desktop; it now ends with compact category entry points instead of eight article-like shelves.

The real notebook initially lacked its derived SQLite index. After rebuilding that local index from existing archives, 122 cited source excerpts and 15 cited conversations became available in the snapshot. Nothing was uploaded. Other citations still show the source description and state plainly when the original body is unavailable.

## Remaining product bar

This preview makes the ten audited areas substantially more usable but does not close their full acceptance criteria. In particular, short-name relations are navigation hints rather than verified semantic edges; the focused record cards are a first type-specific layer over Markdown; claim comparison covers cited keyed Facts and Contact values, not prose; the conversation view is bounded to the latest twelve archived messages; and recall feedback is not durable. A follow-up audit should test quiet, conflicted and empty records, verify relationship correctness with the owner, and improve the living nightly-to-morning workflow.
