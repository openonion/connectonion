# Naming REM concepts

**Decision (2026-11-19, approved by the owner).** In REM's knowledge graph the
only kind of point is the page. A tag is a word that links pages. A tag that
names a person, organisation or project links to that page. A tag that names no
page and that two or more pages share gets a tag page, written by `co rem
investigate tag NAME`. Every command names the kind first, then the page. This
record is for #3140, which a five-expert panel reviewed.

## Words

These words open `co rem tag --help` and `co rem investigate --help`, word for word:

```
Words:
  page             One thing REM knows: a person, organisation, project, tag, skill or decision.
  tag (= topic)    A word that links pages. "co rem tag" puts tags on pages; "investigate tag X"
                   reads every page carrying X and writes X's tag page.
  knowledge graph  Every page and the links between them. Each tag page is a page in it;
                   tags are how pages connect.
  entity           Not used in REM. It means any page in the knowledge graph.
```

Every new REM concept is named by these principles before it reaches a help
page or the reader (owner, 2026-11-19: «用什么样的单词、什么样的句子、什么样的简单表达»).

## Principles

1. **The user's words, never the data structure's.** No bare "graph", and no
   "node", "entity", "edge" or "orphan" in anything a person reads.
2. **One concept, one name; one name, one concept.**
3. **The word works both ways**: as an attribute ("this page is tagged 3900")
   and as a place ("3900's tag page").
4. **The whole and the part each get one name**, like a map and a place on it.
5. **Short, and paired across languages.**

## Precedents

- **Roam / Logseq**: a #tag *is* a page; `#UNSW` and `[[UNSW]]` are the same
  link, and both open UNSW's page. This is the closest precedent.
- **Stack Overflow**: each tag has a written tag wiki, which is our tag page.
- **Wikipedia**: a category is a page, and articles link into it.
- **Notion**: a relation links to another page, not to a label.
- **Gmail**: one word, "label", for the concept everywhere.
- **Google's Knowledge Graph**: people see a knowledge panel, never "node" or "entity".
- **Counter-example: Linear labels.** They are filters with nothing behind them.

## The CLI

| Command | What it does |
|---|---|
| `co rem tag` | Tag every page that has no tag yet; a tag naming a person, organisation or project links to its page |
| `co rem tag person "Jalaj Jain"` | Tag one page |
| `co rem investigate person "Jalaj Jain"` | Write or append one page (also `org`, `project`, `skill`, `decision`) |
| `co rem investigate tag "AI Agent"` | Write or append that tag's page from every page carrying it |
| `co rem investigate people` / `tags` | Every due page of that kind |
| `topic` / `topics` | The same words as `tag` / `tags` |

- A name matches titles and aliases without regard to case or spaces.
- Two matches are refused, with both full names. An unknown kind is refused,
  with the list of kinds. Nothing is guessed.
- The old path form (`people/x.md`) still works but is not taught.
- Tag pages live in `knowledge/`. Knowledge entries merge into tag pages, and
  the reader, the knowledge graph and page review already treat `knowledge/` as
  pages, so nothing moves.

| | 中文 | English |
|---|---|---|
| the whole network | 知识图谱 | knowledge graph |
| a point on it | 页面: 人物 · 组织 · 项目 · 标签页 · 技能 · 决定 · 原则 | page: person · organisation · project · tag page · skill · decision · principle |
| what links pages | 标签 | tag (= topic) |
| a tag's own page | 标签页 | tag page |

## Rejected, and why

- **"graph" alone, and "node"**: these are data-structure words (principle 1).
  rc31 drew a hexagon tag node, so one thing had two points (principle 2).
- **"entity" / 实体**: the same, and it names nothing a person can open. The
  glossary says what it would mean. A legal entity in a contract is fine.
- **"topic" / 主题 as the canonical word**: the panel chose tag, because
  putting tags on pages and writing a tag's page should share one word
  (principle 2). "topic" stays an accepted alias.
- **Bare names** (`co rem investigate "AI Agent"`): ambiguous between a person, a
  project and a tag of the same name. So the kind comes first.
- **Decisions and principles as tags**: they are statements, so they keep
  their own kinds.

## Where this is enforced

- `tests/unit/test_rem_reader_graph_words.py`: no Chinese string says 图谱
  without 知识, no English string says "graph" without "knowledge", and none
  says 节点 / 实体 / node / entity.
- `tests/unit/test_rem_named_pages.py`:
  - each kind resolves, and topic means tag
  - an ambiguous name lists its candidates
  - an unknown kind lists the kinds
  - the plural runs the category, and the old path still works
  - both help pages open with this glossary
- `tests/unit/test_rem_tag_nodes.py`: the owner's example. Three tags link to
  their pages, one gets a tag page, and a single-page tag stays a link.
