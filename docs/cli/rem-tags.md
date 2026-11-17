# Tags: one vocabulary that organises the notebook (#3093)

The owner, 2026-11-17: "Tags are the same as the knowledge graph." He wants to
mark every open item of course 9900 done at once without ever typing a tag.
So a stage of its own, `co rem tag`, reads pages and writes their tags from one
vocabulary; open items inherit their record's tags; the graph gets a node per
tag; search resolves `tag:9900` through aliases.

## What exists where

| Piece | Where | Status |
|---|---|---|
| The `- Tags:` line, its parser and writer | `connectonion/rem/tags.py` | built |
| The vocabulary, aliases and `resolve` | `connectonion/rem/tags.py`, `.state/tags.json` | built |
| The stage: batches, prompt, review, promotion | `connectonion/rem/tag_stage.py` | built |
| The prompt | `connectonion/useful_skills/rem-tag/SKILL.md` | built |
| `co rem tag [--pages N]` | `cli/commands/rem_commands.py`, `rem_help.md` | built |
| A share of every catchup round, `limits.tags_per_round` | `native_round.py` | built |
| `Tag:` line in `co rem status` | `stages.py` | built |
| Tags on open items (`today_queue[].tags`) | `today.py` | built |
| Tag nodes and edges (`graph.tags`) | `reader_model.py` | built |
| Chips, tag pages, `tag:` in search, graph drawing | `reader.html` | **not built**: the reader branch, on the contract below |
| Tags on decisions, knowledge, principles | Abstract | **not built**: those pages have no Facts block |

## Data

**The page is the source of truth.** A tagged page carries one line, the last
line of its `## Facts` section, in the format session pages already use:

    - Tags: 9900 [3], student [3], harbour-university [1]

- Tags are **slugs**, comma-separated, each optionally followed by the `[n]`
  citation of the page line that supports it (the citation that line carries;
  none when the line has none). Session pages keep their uncited
  `- Tags: email, deploy` and are read by the same parser.
- A slug is lowercase, letters, digits and `-`, at most 40 characters:
  `normalise("Capstone 9900") == "capstone-9900"` (the session rule).
- Only the stage writes the line. Investigation keeps a Facts label the page
  already had (`facts.drop_foreign_labels`), and if a rewrite drops or changes
  the page, the page is waiting to be tagged again (below).

**The vocabulary** is `.state/tags.json`:

    {"tags": {"9900": {"label": "COMP9900", "kind": "course", "aliases": ["comp9900"]}}}

- `kind` is one of a closed list, `TAG_KINDS`: `course`, `team`, `organisation`,
  `project`, `role`, `topic`, `place`. There is no `person` kind: a tag is never
  a person's name.
- A **course** tag's slug is its number, as the owner says it (`9900`, `3900`);
  its label is the code (`COMP9900`) and the code is an alias.
- Every notebook starts with the common roles (`ROLES`: student, tutor,
  lecturer, colleague, client, investor, partner, supplier, candidate,
  recruiter, mentor, founder, advisor), so a person's commonest tag is never new.
  Added after the first real trial, where people got topics and no roles.
- Counts are not stored: `vocabulary(root)` counts the Tags lines of every page
  each time, so a count can never disagree with the pages.
- **Session tags migrate without rewriting a session page**: every slug in
  `.state/session-tags.json` that `tags.json` does not hold is read as a
  `topic` tag labelled with its slug. The session summary keeps writing its own
  line; its tags join the same vocabulary, counts and graph.

**Aliases.** `resolve(vocabulary, text)` normalises `text` and returns the slug
whose slug, label (normalised) or alias equals it, else `None`. So `9900`,
`COMP9900`, `comp9900` and `tag:9900` all resolve to `9900`. A new tag the model
proposes that resolves to an existing one *is* that one: it is merged, not
added. An alias is added only by the stage (a proposal's `aliases`) or by hand
in `tags.json`.

**Staying small.** Reuse first: the prompt hands over the vocabulary, most-used
first, and says a new tag is the exception. Per page at most `PER_PAGE` (8)
tags; per turn at most `NEW_PER_TURN` (8) new tags. A new tag needs a kind from
the list, a label, a slug that is not a catch-all (`CATCH_ALL`: misc, general,
other, workflow, platform, tools, automation, people, contact, work) and not a
person's page name.

## The stage: `co rem tag`

- **Reads pages, never sources** (like `rem-abstract`). Pages are people,
  organisations and projects with a `## Facts` section.
- **Waiting** = a written page (not a stub the map made alone, `census.written`) whose text, without its Tags line, has a different hash
  from the one saved in `.state/tag-pages.json` when it was last tagged. So a
  page that was never tagged waits, and a page investigation or deepen changed
  waits again: re-tagging after those stages needs no extra wiring.
- **Batches**: `BATCH` (20) pages a turn. Each page is handed as a file
  `pages/pN.md`: the page without its Sources section, stamp or old Tags line,
  at most `EXCERPT` (5,000) characters. The vocabulary is `vocabulary.json`.
- **Output**: one JSON file, `candidate.json`:

      {"pages": [{"id": "p1", "tags": [{"tag": "9900", "evidence": "Student in COMP9900, team F13 [3]"}]}],
       "new_tags": [{"tag": "9900", "label": "COMP9900", "kind": "course", "aliases": ["comp9900"]}]}

- **Review** (`tag_stage.check`), per tag; a refused tag is dropped and named in
  the run record, the page's other tags are kept:
  - `no evidence`: the evidence is not text of that page (whitespace and case
    ignored, Markdown link targets dropped);
  - `not named`: a course, team, organisation, project or place tag whose
    evidence does not contain its slug, label or an alias (a course: its number);
  - `not in vocabulary`: neither an existing tag nor proposed in `new_tags`;
  - `bad new tag`: a kind off the list, a catch-all, a person's page name, a
    malformed slug, or past the turn's cap;
  - `too many`: past `PER_PAGE`.
  The whole reply is refused (the batch waits for the next turn) when it is not
  JSON or does not return every id exactly once.
- **Promotion** writes only the Tags line: `with_tags(page, line)` then
  `only_tags_changed(before, after)` must hold, or nothing is written. A page
  that changed between preparation and promotion is skipped and stays waiting.
  A page with no accepted tag gets no line but is marked tagged, so it does not
  come back every round.
- **Model**: level 1 (`STAGE_LEVELS["tag"]`), the cheapest: short, structured,
  checked by code.

## Scheduling

- Alone: `co rem tag [--pages N]` tags up to N waiting pages (default 200).
- In every round (`co rem exec`, `co rem catchup`): one tag turn between two
  portions of investigation, after translation's share; after the queue, tag
  turns go on until no page waits, up to `limits.tags_per_round` pages (400). A
  batch whose reply was refused is not offered again in the same round.
- `co rem status`: `Tag: N untagged pages waiting; last ran DATE` and, while
  pages wait, `; a round tags up to 400`.
- The catchup night line counts `N pages tagged`.

## Contract for the reader (reader.html is not changed by this work)

Every field is new; the current reader ignores all of them.

- `data.tags`: the vocabulary with counts,
  `{slug: {"label", "kind", "aliases": [...], "count"}}`.
- `records[].tags`: the slugs on that page, in page order (`[]` when none).
- `today_queue[].tags`: the open item's tags: its record's tags, then the tags
  of every person and organisation page its text links to, without repeats.
  Waiting filters by these, and "close all 9900" is the existing per-key done
  mark applied to every row whose `tags` holds `9900` (each row's `keys`).
- `graph.tags`: `{"nodes": [...], "edges": [...]}` beside `graph.nodes`:
  - node `{"id": "tag:9900", "kind": "tag", "label": "COMP9900", "tag_kind": "course", "count": 14}`
    for every tag on at least one drawn node;
  - edge `{"source": "people/x.md", "target": "tag:9900", "kind": "tagged"}`
    for every tag on a drawn node (not a folded session, not a private record).
- **Search**: `tag:QUERY` resolves exactly as `tags.resolve` does: normalise
  QUERY (lowercase; spaces and `_` to `-`; drop other punctuation; collapse
  `-`), then match a slug, then a normalised label, then an alias. Python:
  `tags.resolve(vocabulary, "tag:comp9900") == "9900"` and
  `tags.matching(records, vocabulary, "tag:9900")` lists the records.
