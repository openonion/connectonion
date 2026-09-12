# 066 — The notebook is built in layers, and the Skills are two axes

Status: accepted 2026-09-12. Supersedes the single-pass shape in
[065](./065-ai-owned-wiki.md), which still describes the runner and the
sources correctly.

## What went wrong with one pass over the timeline

The first real run read a 60-day mailbox forward, batch by batch, and wrote a
page for whoever appeared in each batch. It produced **143 pages whose people
half had a median of 700 bytes, twenty of them a single line**. Nothing was
broken: each page was a faithful record of the few messages that happened to
be in front of the maintainer when it met that person.

That is the flaw. Walking the timeline means meeting every subject in slices,
so breadth arrives first and depth never does. It also means identity has to
be re-guessed on every batch, which is how "odi" became a second page for a
person the notebook already held as "Ody Zhou".

## Entries are not all found the same way

The test that separates them: **when a new one comes into being, does some
system mint an identifier for it?**

| | Where the roster already exists | Measured here |
|---|---|---|
| `people` | mail correspondents | 121 from 645 mails |
| `projects` | session `cwd`, git repositories | 54 (Claude, with date ranges), 26 local repos |
| `skills` | the `SKILL.md` files themselves | 316 |
| `works` | commits, published artifacts | 1134 in three months |

Nothing mints an identifier for a decision, a principle, or a piece of
knowledge. Those exist only as sentences, and must be read out.

**Decisions look like an exception and are not.** There is no registry of
decisions, but there is a registry of the artifacts that *closed* them: a
merged pull request, a sent mail, a signed document, a released tag. Those
enumerate precisely — and far too generously. Of 400 merged pull requests in
five weeks, roughly 30 carry the signal that distinguishes a decision from
work: **an alternative was rejected**. So the registry supplies candidates and
the rejected alternative filters them.

The entry key follows from that: **a decision page is one settled question**,
not one artifact. Three pull requests about where the notebook is stored are
one page, and a later reversal edits it rather than opening a second.

**Principles are second order.** A principle is a reason that recurs across
decisions; it is never stated once in any source, which is why it cannot be
extracted from one. Threshold: three decisions sharing a reason. Two is a
coincidence, one is an opinion.

## Categories: seven stored, two computed, one removed

`agenda` and `opportunities` are dropped as stored categories. Every entity
page already carries `Open threads` and a state; agenda is their union and an
opportunity is an entity that has not closed. Writing them separately produced
the same commitment twice in two wordings. They become views.

`notes` is removed. It had neither a roster nor a definition, so it became the
bin for anything that did not fit — a real run put a page there on its first
batch.

Stored: `people`, `projects`, `skills`, `works`, `decisions`, `knowledge`,
`principles`.

## Four stages, and only three of them touch a source

```
map          enumerate the rosters              no model, no Skill — this is code
investigate  one subject, every source at once  few pages, each finished
abstract     pages in, pages out                decisions ← episodes
                                                principles ← decisions
maintain     today's new material               append to the page that exists
```

`map` needs no Skill because enumeration is `find` and field-reading.
`investigate` is the first-run mode: identity is an *input*, so nothing is
guessed. `maintain` is the steady state and must not rewrite a page it should
be extending.

## The Skills are two independent axes

A stage says **what to produce**. A source says **where the user's words are in
that store and how it lies about them** — Codex files harness output under
`role: user` (97% of it, measured), mail arrives with both sides, Claude Code
leaks subagent prompts.

Writing one file per pair is four sources times four stages, and a fifth source
would cost four files. Composing them costs one:

```
useful_skills/
  wiki-extract/          wiki-source-codex/
  wiki-maintain/         wiki-source-claude-code/
  wiki-investigate/      wiki-source-outlook/
  wiki-abstract/         wiki-source-gmail/

instructions(stage, kind) -> stage Skill  [+ "\n---\n" + source Skill]
```

`abstract` takes no source and must refuse one: its input is pages the notebook
already holds, and a stage that reads pages has no business knowing which store
they came from. That asymmetry is the check on whether the split is real, and
it is asserted in `tests/unit/test_wiki_instructions.py`.

Flat directories with a prefix, not nested folders: the Skill loader discovers
`.co/skills/<name>/SKILL.md` one level deep only, so `wiki/sources/codex/` would
be invisible to `co ai "/wiki-investigate"`.

## First run, end to end

```
co wiki map          121 people · 54 projects · 316 skills · 1134 works    free
   → the user picks a handful
co wiki investigate  each picked subject, every source at once             paid
   → few pages, each complete
   (time passes; episodes accumulate)
co wiki abstract     decisions, then principles from them                  paid
```

The expensive stage runs over the handful the user chose, not over 121 people.
