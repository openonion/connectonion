# Naming REM concepts

Every new concept in REM is named by these principles before it reaches a help
page or the reader (owner, 2026-11-19, #3140: «用什么样的单词、什么样的句子、什么样的简单表达»).

## Principles

1. **The user's words, never the data structure's.** No bare "graph", and no
   "node", "entity", "edge" or "orphan" in anything a person reads.
2. **One concept, one name; one name, one concept.**
3. **The word works both ways**: as an attribute ("this page is tagged 3900")
   and as a place ("3900's tag page").
4. **The whole and the part each get one name**, like a map and a place on it.
5. **Short, and paired across languages.**

## Precedent

- **Roam / Logseq**: a #tag *is* a page. This is the closest precedent.
- **Stack Overflow**: each tag has a written tag wiki.
- **Wikipedia**: a category is a page.
- **Gmail**: one word, "label", for the concept everywhere.
- **Google's Knowledge Graph**: people see a knowledge panel, never "node" or "entity".
- **Counter-example: Linear labels.** They are filters with nothing behind them.

## The names

| | 中文 | English |
|---|---|---|
| the whole network | 知识图谱 | knowledge graph |
| a point on it | 标签 | tag |
| its page | 标签页 | tag page |
| the line between points | (unnamed) | (unnamed) |
| the command | `co rem tag` | `co rem tag` |

- **Considered and rejected: "topic / 主题" for a point.** It reads well as a
  place, but it would make tagging and visiting two different names (principle 2).
- **Knowledge entries merge into their tag pages**, so the word 条目 / "entry"
  goes for them.
- **Decisions and principles stay their own kinds.** They are statements, not
  topics, and they carry tags like any page.

## Where this is enforced

- `tests/unit/test_rem_reader_graph_words.py`: no Chinese string says 图谱
  without 知识, and no English string says "graph" without "knowledge".
- `co rem tag --help`: "tag" and "tag page", never "node".
