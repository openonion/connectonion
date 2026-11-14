# REM category heading audit (#2994, #2996)

This is a source audit of the category renderers, not a claim of rendered or
real-notebook review. English strings below also identify their Chinese versions.
Record titles, record prose, table columns, filters, buttons and chart legends
retain their meaning and remain available.

| Page / renderer | Heading or subtitle | Decision and reason |
| --- | --- | --- |
| Every generic category (`category`) | Contents / Category breadcrumb | Drop: repeats navigation rather than identifying content. |
| Every generic category | Category name; written/mapped count | Keep: names the collection and reports its size, on one line. |
| People (`peopleView`) | People | Keep: names the table; no explanatory subtitle is rendered. |
| People | Who is this, and where did we leave off? | Drop obsolete generic subtitle; the table already exposes contact and open items. |
| Organisations (`orgsView`) | Organisations eyebrow; N organisations | Keep: compact collection label and factual count. |
| Organisations | Companies, teams, and groups we correspond with | Drop obsolete generic subtitle. |
| Organisations groups | Waiting on you / Recently in touch / Quiet; count | Keep: names each group. Small age thresholds remain because they define group membership. |
| Projects (`projectsView`) | Projects; count; Timeline / Board / List | Keep: names collection and actual view choices. |
| Projects | Why, where are we, how to continue? | Drop obsolete generic subtitle. |
| Projects | Sorted by health; a sub-project sits under its project | Drop: order and indentation carry this information. |
| Projects | The board's axis is a question | Drop: the adjacent choices already name the axes. |
| Projects | Dynamic activity / overdue summary (`projectLede`) | Shrink to body size: these are notebook facts, not instructions about reading the layout. |
| Projects | Snapshot provenance; coverage counts; inference labels | Keep small: identifies evidence, missing coverage and inferred rather than observed information. |
| Projects groups / board columns | Health states, ownership groups, merge-signal kinds, counts and thresholds | Keep: names groups and defines the rules behind inferred status; not a page introduction. |
| Skills (`skillsView`) | Skills | Keep beside finder: collection name; finder contains count. |
| Skills | What your agents can do, the ones you use most first | Drop: first and larger cards already show priority. |
| Skills | Most used | Drop: the cards precede the index. |
| Skills | Everything they can do | Drop visible caption; retain navigation's accessible name. |
| Skills families | Family names and counts | Keep: names jump targets and groups. Name-only skill notice remains a data-completeness status. |
| Knowledge (`topicList`) | N knowledge entries / No knowledge yet | Replace with Knowledge and Entries / Graph controls: names the place and its views. |
| Knowledge | Subjects that tie your records together: a market, a course, a way of working | Drop: topic rows and linked entities convey this directly. |
| Knowledge | See them in the graph | Replace with Graph control in the shared view switch. |
| Knowledge empty | A knowledge entry is filed when a subject recurs across your notes; none has yet | Drop; retain the small night-run empty-state status, explaining when content will arrive. |
| Knowledge graph (`graphHead`, `graphPanelGuide`) | All records; N records linked together; N not linked yet | Replace title with Knowledge; numerical information remains in legend. |
| Knowledge graph | Whole map; Click a point to see what it connects; Knowledge is the thread… Start with one entry | Drop: map, search and linked page rows are the content. |
| Knowledge graph panel | Knowledge; Most connected | Drop introductory group headings; topic rows precede busiest pages with a divider. Focused page names and relationship-kind headings remain. |
| Opportunities | Opportunities; count | Keep collection name and count; drop Worth exploring, not yet committed. |
| Decisions | Decisions; count | Keep collection name and count; drop What we chose and why. |
| Principles | Principles; count | Keep collection name and count; drop Standing rules we adopted. |
| Works | Works; count | Keep collection name and count; drop Outputs that can be reused or shown. |
| Agenda (`agendaView`) | Promises, waiting on others, dates that matter | Drop obsolete generic subtitle. Calendar already starts with date navigation, no large page introduction. |
| Agenda | Date range, day headings, Still open from earlier | Keep: names times and the carry-over group. Calendar availability/error notices remain factual status. |
| Agent sessions (`sessionsView`) | Agent sessions; N sessions | Keep collection label and count; day headings name date groups. |
| Agent sessions | What you worked on with your coding agents | Drop: session rows show conversations and their projects directly. |
| Agent sessions empty | Queued for tonight / background updates off | Keep small: explains actual pending state, not the layout. |
| AI notes / Maps | Category label; count | Keep if directly addressed; both are accessed through Activity rather than memory navigation. No generic explanatory subtitle remains. |
| Today (also touched) | Waiting count; thing(s) waiting on you | Keep: defines what the actionable number counts. |
| Today | Start with this person / these N people | Drop: the adjacent faces and selected card show where to start. |

## Former All records paths (#2996)

- The wiki remains `#c=knowledge`, one entry per topic, with linked entity chips.
- The complete linked graph remains `#view=graph`, reached by Knowledge's Graph
  control and the command palette. Focus URLs still work. `#c=all` remains a
  compatibility bookmark to this graph, activating the Knowledge rail item.
- The combined list is retired. Its `listedRecords()` inventory remains in the
  corresponding People, Organisations, Projects, Skills or Knowledge rail place,
  or Opportunities, Decisions, Principles, Works, Agenda and Agent sessions under
  More. Search includes isolated records too; graph membership is not required.
- AI notes and Maps were already excluded from All records and remain in Activity,
  reached from Memory changes. Catalogue parents and held/private exclusions keep
  their existing filtering; this change does not introduce a new store or filter.

Browser coverage: `test_rem_knowledge_place_browser.py` checks the rail in both
languages and sizes, entry/entity paths, graph and old bookmarks, category
reachability, isolated-record search and removed text via `inner_text`.
The real-notebook before/after screenshots and independent visual review remain
required before accepting this work; a source audit cannot establish visual quality.
