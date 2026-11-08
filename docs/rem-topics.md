# REM topics and graph snapshot

`co rem scan topics` reads existing notebook pages and `.state/extracts/` without
a model or writes. `build_map` calls `topic_map.map_topics` under the maintenance
lock and files qualifying candidates in `knowledge/`. `co rem investigate topics`
uses the normal investigation queue, with `rem-page-topic` and aliases as handles.
Mail searches include body text, bounded to 500 provider results per alias; saved
local bodies are searched too. Coverage reports the provider bound.

A candidate needs three distinct source IDs spanning at least fourteen days and
two existing record paths, or an affirmative owner remember/learn request naming
that topic. Repeated digests and page citations do not create sources. Topics
blocks carry `name | semicolon-separated aliases | concerned record path |
speaker, date, source id | sentence`. Completed extractions retain their Topics
block even when the task directory is temporary. Older Knowledge/Insight notes
can supply explicit bold subjects and Knowledge headings; matching page sentences
must carry their own dated source citations. Conflicting dates for the same source do not establish duration. Undated matches do not meet a date
threshold. No names from a particular notebook are shipped as a topic catalogue.

Exact aliases group transitively, with no fuzzy merges. Existing duplicate topic
pages use `merge.merge_into`, retaining old paths in `.state/aliases.json` and
archiving the merged page. Investigation writes relative links only on the topic
page; `relationships()` supplies reverse `linked from` rows with the same sentence
and citations. Sessions and skills are counted rather than linked from a topic.
Alias-only page matches become pending yes/no link reviews. Yes writes only the
topic end, with the owner's review as provenance. No records a negative match and
is not proposed repeatedly. Source-backed relevance still needs investigation;
a stub does not assert links merely because it met the threshold.

Health, family, personal money and legal/immigration topics are marked
`[personal]` on the title. Health requires explicit owner-health attribution;
ambiguous and third-party health evidence stays out. Private topic pages, incoming
relations, searches and reviews respect the local reader curtain. Shared reader
snapshots omit private topics and their reviews. Graph titles are blank for
private nodes. Handoff strips a complete notebook page with a private title before
masking or serializing conversation text; prose paraphrases still pass through the
existing handoff private-sentence review.

## Snapshot contract

Full `reader.snapshot()` includes `graph` (Today's small shell defers it):

```json
{
  "nodes": [
    {"id": "knowledge/thermal-storage.md", "kind": "knowledge",
     "title": "Thermal storage", "degree": 1, "has_owed": false, "private": false}
  ],
  "edges": [
    {"source": "knowledge/thermal-storage.md", "target": "people/mara.md", "kind": "topic"}
  ],
  "folded_sessions": 12,
  "unconnected": {"count": 3, "by_kind": {"people": 2, "skills": 1}}
}
```

Node IDs are notebook-relative paths and kinds are top-level folders. All entity records
except generated logs/notes and the skill catalogue index are present, including degree-zero records.
Consumers draw connected nodes and disclose the unconnected count/list separately.
Edges are undirected, sorted by endpoint and deduplicated; `kind` is `topic` if
either endpoint is knowledge, otherwise `linked`. Mention hints are excluded.
A session with an explicit project link is folded into that project; its remaining
edges are rewired to the project, self-edges dropped. If several projects are
linked, the lexically first path is the deterministic home. Unassigned sessions
remain nodes. Degree is computed after folding. `has_owed` reads explicit owner
owes language from Open threads. A private node has an empty title; keep it grey
and unlabelled. Graph data contains no private snippets.

Session and skill counts include uncited alias mentions; those mentions do not
add qualification sources or establish links.

Each knowledge record also has `topic`: `aliases`, `sessions`, `skills`, `first`,
`last`, and `doubtful` (record path plus sentence), derived from the last map.
The full topic anatomy and settled canvas graph are a separate reader UI layer;
this change provides the mechanism, privacy boundaries and snapshot contract.
