# REM reader: page and interaction audit (1 October 2026)

This is a design review of the **1.9.0a11 reader** using the invented notebook in
`tests/fixtures/rem_reader_notebook.py`. No private notebook content is in these
screenshots. The review covered home, People, person (written and mapped), project,
organisation, skill, search, and empty category in Chrome at 1440 × 900 and
390 × 844, with light and dark schemes. It also checked the reader's rendering
code and the earlier read-only real-notebook audit in #2060. A fixture reveals
the interaction and layout; its record counts do not represent a real user's data.

The product bar is specific to the REM name: after a night pass, the owner should
see what memory changed, follow connected context, and rehearse what matters.
The current reader has useful work already: a morning card, open-thread direction,
a People table, source jump links, and a dated history spine. The issues below
are what still makes it feel like a rendered notebook instead of a mature memory
product. This is a review of screens and behavior, not a claim that a named
designer participated.

## Ten highest-priority issues

| Rank | Problem and observed evidence | Design outcome | Issue |
| --- | --- | --- | --- |
| 1 | **Detail pages are articles with small UI islands.** Mara's page has 11 H2 sections and 2,098 characters in the note; it is 2,529 px tall on desktop and 4,051 px on phone. The open threads and fact card are useful, but the relationship, decisions, history, and sources are still a vertical essay. [Desktop](person-light-desktop.png) · [phone](person-light-phone.png). | Different record types need their own task-first templates. A person opens on relationship, open loops, and change; a project opens on state, people, next decision, and trajectory; the long note becomes a deeper layer. | #2065 |
| 2 | **Named entities are not reliable navigation.** In the invented Harbour project, Mara and Fernhill are named but there are no cross-record links in the main note. The earlier real-notebook audit found only 2 of 381 people pages with a link and no project links. The single Mara→Fernhill fixture link proves the reader can render links, but generation does not make them dependable. [Project](project-light-desktop.png). | Recognize verified person, organisation, and project references; give every relationship a bidirectional record link and a useful related-context area. Do not link ambiguous names automatically. | #2060 |
| 3 | **History is a list of dated sentences.** Mara's five-event history is a fine chronological spine, but the user cannot filter by conversation, decision, promise, source, or period; the event itself cannot open the underlying interaction. On phone it is a tiny section deep in a 4,051 px page. [Person](person-light-phone.png). | A visual activity view groups events by day and type, highlights meaningful turns, and opens exact evidence or conversation context. | #2103 |
| 4 | **The hero cannot say what REM learned overnight.** “Updated in the latest pass” labels current page statements; it does not compare claim before/after, so a rewrite can look like a discovery. [Home](home-light-desktop.png). | Show a verified change, correction, or quiet night with evidence and previous/current state. | #2096 |
| 5 | **Connections are text, not an explorable model.** The home has one “Connected context” pair, while a person, project, and company appear separately with no navigable neighborhood or connection reason. [Home](home-light-desktop.png) · [project](project-light-desktop.png). | Show a focused relationship map and connection cards with direction, reason, confidence, and direct hops. | #2066 |
| 6 | **The phone spends its first screen on a fact inventory.** On Mara and Harbour, a tall card of mostly secondary fields and “not found” entries precedes the insight, activity, and project status. On the mapped person, almost the whole page is a 14-field fact card with 9 absent values. [Person](person-light-phone.png) · [mapped person](person-mapped-light-desktop.png) · [project](project-light-phone.png). | Use a compact summary with the 2–4 fields needed now; collapse the rest, distinguish “unknown” from “not searched,” and bring the current action above the inventory. | #2104 |
| 7 | **The project is not a project workspace.** Harbour has a text “Where it stands,” an ASCII diagram, threads, paths, and four source IDs, but no linked owner, no visible people or company, no stage/health, and no timeline of decisions. The fact card says People and Organisation are “not found” although the prose names Mara and Fernhill. [Project](project-light-desktop.png). | Make state, people, dependencies, decision, and next step first-class, source-backed project components. Resolve contradictions before showing a field as absent. | #2105 |
| 8 | **Citations stop at a source inventory.** Clicking a superscript jumps to a short source line with an opaque ID. It cannot reveal the original message, passage, or side-by-side support for a claim. [Person](person-light-desktop.png) · [project](project-light-desktop.png). | Open an evidence panel at the claim, showing quoted span, timestamp, source identity, and conflicts; preserve local privacy. | #2106 |
| 9 | **Search is literal and record-only.** A query for “pilot” returns four page snippets grouped by file category; there is no thread/decision/source result and no path from “Who do I owe?” to the existing obligation data. [Search](search-light-desktop.png). | Search owner tasks and typed memory objects, explain matches, and let results land on the exact claim or thread. | #2098 |
| 10 | **The visual language does not express the memory system.** A moon-square logo and dark home panel evoke night, but every record reverts to the same pale article, serif headings, and small mono metadata. The semantic transitions—sleep to morning, uncertain to supported, one memory to connected context—have no consistent visual grammar. [Home](home-light-desktop.png) · [person](person-light-desktop.png) · [skill](skill-light-desktop.png). | Establish a restrained REM identity with a distinctive mark, type/colour/motion rules, and reusable states for evidence, change, connection, and recall; validate it across record types and phone, including reduced motion. | #2107 |

## Six more material problems

11. **Skill pages report a total, not a usage story.** “14 invocations in 180 days” and a progress bar do not show when use rose or fell, which project used it, or what result it had. [Skill](skill-light-desktop.png).
12. **Mapped pages show a template-shaped absence.** A mapped person opens to a large “Only mapped so far” command box and a wall of empty fields, rather than explaining what is known, why the person surfaced, and what one investigation might answer. [Mapped person](person-mapped-light-desktop.png).
13. **Navigation exposes storage taxonomy before morning intent.** The left rail begins with Notebook, Contents, People, Organisations, Projects, Skills. Home asks about today, but there is no persistent Today, Open threads, Changed, or Explore view. [Home](home-light-desktop.png).
14. **The HTML snapshot makes freshness hard to judge.** The rail says “Snapshot” and “co rem open re-renders.” The reader has no in-view refresh or update history, so a returning user must use a terminal to see whether it reflects the latest night.
15. **The strongest actions are copy commands.** An investigated page can expose an obligation, but the main interactive actions remain navigation, citation jump, and copying a command. The owner cannot mark a thread resolved, correct memory, or ask a follow-up in the reader.
16. **Long pages create a reading and accessibility burden.** At phone width, the person page is almost five viewports tall; a seven-section project is over three. Small mono metadata, repeated section headings, long source IDs, and an ASCII project diagram require concentrated reading and can make scanning and assistive navigation harder. This warrants task tests and contrast/focus verification, rather than decoration alone.

## Review method and next design gate

The browser measurements above used `scripts/capture_rem_reader.py` and
Playwright against the invented fixture. Screenshots show real rendered HTML at
the stated widths. Browser inspection confirmed no horizontal document overflow
on the captured routes, so the central problem is hierarchy and interaction,
not a broken responsive breakpoint. The mobile project diagram stays a clipped
code block, which needs its own presentation.

For each redesign PR: show before/after screenshots for written and mapped
records on desktop and phone; walk the first-click paths for “what changed,”
“who do I owe,” “why do I know this,” and “what connects this project”; then
test source access, keyboard focus, reduced motion, and data truthfulness. The
release is ready only when these flows work on a realistic notebook copy as
well as the invented fixture.
