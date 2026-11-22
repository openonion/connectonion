# The REM reader's visual system

Status: in force for Projects (the three views and the project record) since #3096. The other places are
being brought onto it one at a time; `tests/unit/test_rem_reader_visual_system.py` counts what is left in
each and fails when a count goes up. When you fix a place, lower its number in that test in the same change
and update the table at the end of this page.

The reader is one HTML file, `connectonion/rem/reader.html`. Every value below is a custom property in the
token sheet at the top of that file (between `/* fuse:tokens */` and `/* /fuse:tokens */`). Nothing outside
the sheet may write a size, a family, a weight, a colour, a radius, a shadow or a duration
(`tests/unit/test_rem_reader_style_sheet.py`). This page says what each token is *for*, which a lint cannot.

## The rules a page is judged by

1. One hierarchy per screen. One thing is largest; everything else is body or smaller.
2. Type carries structure. A level is a step of the scale or a change of weight, never a new family, a box
   or a tint.
3. Colour carries meaning. Ink and its greys are the page. Green and red each mean one thing (below) and are
   never decoration.
4. Nothing a person reads is smaller than 13px, and nothing they read as a sentence or in a table is smaller
   than 15px.

## Type

Two families, both local on purpose (the reader makes no network call):

| Token | Stack | For |
|---|---|---|
| `--font` | -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", Inter, sans-serif | everything. Latin first, then the Chinese faces, so mixed lines share one baseline |
| `--mono` | ui-monospace, "SF Mono", Menlo, monospace | code and file paths only. A number in a table is `--font` with tabular figures, not mono |

Seven sizes:

| Token | Size | For | Leading |
|---|---|---|---|
| `--s-display` | 44px (36 on a phone) | the single display element of a screen: a count or a name | `--lh-tight` |
| `--s-head` | 24px | a page's name, a card's subject, a widget's big number | `--lh-head` |
| `--s-title` | 20px | a page's name on a phone; the head of a section that leads a page | `--lh-head` |
| `--s-lead` | 17px | the one sentence a page opens with | `--lh-read` |
| `--s-body` | 15px | sentences, table cells, a row's name. **The smallest size for a sentence or a cell** | `--lh-body`, `--lh-read` for a paragraph |
| `--s-ui` | 13px | labels, chips, column heads, a date beside a row. **The smallest size for anything read** | `--lh-ui` |
| `--s-meta` | 11px | captions only: an axis tick, a badge on an icon. Never a sentence, never a table cell | `--lh-ui` |

Five steps of leading, as unitless ratios so they scale with the size:

| Token | Ratio | For |
|---|---|---|
| `--lh-tight` | 1.05 | display |
| `--lh-head` | 1.25 | titles and heads |
| `--lh-ui` | 1.4 | a label, or a row of one line |
| `--lh-body` | 1.55 | sentences |
| `--lh-read` | 1.7 | a paragraph, and any running Chinese: Han characters fill the em box and have no descenders to borrow room from, so they need more air than Latin at the same size |

Two weights: `--w-regular` (400) and `--w-bold` (600). Bold is a name or the one thing to act on in a row;
it is not emphasis inside a sentence. No italics for Chinese.

## Spacing

A 4px grid: every gap and padding is a multiple of 4. The named steps are `--u1` 4, `--u2` 8, `--u3` 16,
`--u4` 24, `--u5` 40 and `--u6` 64; 12 and 32 are written out. Inside a row use 4, 8 or 12; between rows 12 or
16; between sections 24 or 32. A list's rows share one height so the eye can run down a column.

## Colour

| Token | Light | Meaning |
|---|---|---|
| `--paper` | #ffffff | the only canvas |
| `--ink` | #121512 | text, and the darkest step of any measure |
| `--grey` | #636863 | second ink: what explains a row (a sentence under a name, a date, a column head) |
| `--pencil` | #a3a8a3 | REM's inference: dashed lines and outlines. Never a text colour (2.6:1 on paper) |
| `--rule` | #e8eae7 | hairlines between rows |
| `--well` | #f5f6f4 | an inset: an empty cell, an input, a hovered row |
| `--green` | #22d27a | **the one accent.** Reserved for the single primary action of a screen. A page of records has none, so it has no green |
| `--red` | #c02a17 | overdue, and nothing else |

The **3D knowledge graph** is the one place hue names a kind (#3309): there every mark is a sphere, so colour does
the work shape does on the 2D map. Tag pages take the accent (`--green`, ink in light mode); the other kinds are
four desaturated colours at one lightness (OKLCH L .60 in light, .74 in dark): `--kind-people`, `--kind-orgs`,
`--kind-projects` and `--kind-notes` (sessions share the notes' grey). They are never a call to action, a one-line
legend in the map's header and a dot before each row of its side list name them, and they are read only by the
3D graph (`GRAPH_3D_TONE` and the `.gx-dot` rules); nothing else on any page may use them.

How much of something there was is said in **steps of ink, never in hue**: `--heat-0` (nothing, the well),
`--heat-1`, `--heat-2`, `--heat-3`, `--heat-4` (all of the ink). They are mixed from ink and paper, so the dark
theme follows without a second set. A strip that uses them always says in words what is counted and what a
step means.

Dark is the same names under the two theme selectors; a page never writes a dark value of its own.

## Tables and rows

- Cell text is `--s-body`. Column heads are `--s-ui` in `--grey`.
- A row is a name in bold and at most one sentence in grey. What does not fit in a sentence belongs on the
  record, not in the row.
- Numbers use tabular figures and align right; words align left.
- Status is a word. A dot or a shade may repeat it; it may not replace it.

## Projects, the first place built on it

One idea per view, and the same row in all of them: a name in bold and one sentence in grey, both 15px.

| View | The one idea | What a row holds |
|---|---|---|
| Timeline (`#c=projects&v=timeline`) | a contribution calendar per project | name; a sentence worked out from its weeks ("Busiest in October; quiet for 3 weeks"); a square a week under one axis of named months |
| List (`&v=list`) | the same rows as a table | name and what the project is; status in words; last active; the last 12 weeks; how many open items are in Today |
| Board (`&v=board`, the default) | which state each is in | a card: name, what it is, the last 12 weeks, the last date |
| Record (`#r=projects/...`) | what is known | what it is, where it stands, 26 weeks of activity, what was decided, who is involved, sessions by date, then one line that counts open items and leads to Today |

**What a square counts** (`connectonion/rem/project_activity.py`, said in words on the page): each message
the owner typed to an agent in the project's folders; a recorded session, once, on a day none of its
messages were kept; a mail the page cites, when the notebook holds its date; the day the page gives as last
activity, when nothing else was counted that day. Decisions and commits are not counted: the notebook holds
no date for either yet. A week starts on Monday in the notebook's zone.

**One scale.** The four steps above "nothing" are the quartiles of every project's active weeks taken
together, so a count is the same shade on every row and rows compare. A week before a project's first dated
activity is not drawn, so a row begins where the project does; this week is ringed; weeks to come are outlines.

**Order.** People's rule (newest contact first), for projects: the week it was last active, newest first;
within a week, the busier of the last twelve first; then by name. Projects with no dated activity for more
than 30 days sit below a worded divider. The page says the rule in one line.

**Time has no end stop.** The timeline opens on this week with a year behind it and grows by half a year at
whichever edge is reached. "Today" returns; ← and → move a month; Home returns too.

**Records are not tasks.** A card quotes no request and names no owner; a record has no step rows and no
"mark done". Open work is counted and linked to Today. The note that a translation is not ready closes a
project's record instead of opening it.

**A phone** shows the name and its sentence above the squares, which scroll under them: 14px squares, about
twenty weeks, the same scale.

## What is left, by place

Counted by `inventory()` in the test: `caption` is a declaration at 11px, `leading` a line-height written out
instead of a `--lh-*` step. Families off the two stacks and sizes off the scale are at zero everywhere.
Before #3096 Projects stood at 49 and 25; the whole reader at 468 and 372, now 421 and 347. The Agenda calendar's `.cal-` rules count as Agenda.

| Place | caption | leading |
|---|---|---|
| Projects | 0 | 0 |
| People | 18 | 10 |
| Organisations | 58 | 37 |
| Knowledge | 28 | 25 |
| Agenda | 10 | 8 |
| Sessions | 37 | 39 |
| Today | 25 | 43 |
| Record pages | 42 | 34 |
| Shell and shared | 203 | 151 |
