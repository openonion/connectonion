# A source is a command, and REM keeps nothing from it

Status: decided by the owner on 2026-11-21 (#3249); not yet implemented.

## The problem

Each new REM source (Asana #3034/#3060, Obsidian #3039/#3064, OneNote #3222, Granola #3223) was growing its own
machinery inside REM:
- `if kind == ...` branches in generic code, and a "not registered" line in every investigation prompt for users
  who never chose the source (#3040);
- a shared `source_hooks.Source` protocol of nine functions per source (`status`, `consent`, `pending`, `configure`,
  `fetch`, `collect`, `gather`, `record_of`, `cited`) with a code registry (#3228);
- per-source snapshot stores of everything read, so citations could open "the cited version".

The commands already say most of this. `co rem sources` shows which sources are on and approved, and each source has
its own CLI. Owner, 2026-11-21: "命令行的执行结果就是 status 呀，那为什么还需要在代码层面有这些东西去检测呢？我觉得这是
over engineering" (the command's output *is* the status, so why would code also need these things to check it? I
think this is over-engineering), and: "我们都不存了…每次都从网络上或者从来源加载就可以了" (we don't store any of it… just
load from the network or the source each time).

## Decision

**1. A source is its `co` command.** Besides its own help and commands, REM asks it two things:

```
co <source> changes --since <ISO time> --json   # what is new or changed since then: id, time, title
co <source> show <id> --json                    # one item now: text, author, time, link
```

There is no protocol, no adapter module and no registry. The "kind" is the command's name.

**2. REM saves one fact per source: on or off, with the user's consent.** It lives in the notebook's config
(`subscriptions.json`) and changes only through `co rem sources add/remove`, which `co init` offers once. A source
that is off is never mentioned: no prompt line, no status noise.

**3. Whether a source is usable is checked on every run, never stored.** Usable means the command is installed and
its credential name or folder is present (nothing is decrypted, nothing is fetched). `co init` and `co rem sources`
print what they detect. At night, a source that is on but unusable gets one line in `co rem status` ("Asana: waiting
for co auth asana") and is skipped.

**4. REM keeps nothing from a source after the first scan.** It keeps no snapshots, no copies and no per-source store.
- The first scan, when a source is turned on, may save what it needs to start: the time it last read up to (the
  `--since` cursor for the next run).
- After that, every night stage loads what it needs from the source itself: `changes` to find what is new, `show` to
  read an item. A citation `<source>:<id>` opens through `co <source> show <id>`, live.
- If the item is gone or changed at the source, the citation card says so in one line ("no longer in Obsidian" /
  "changed since it was cited"). REM does not keep a private copy so it can show the old text.

What REM writes is its own pages and the cursor. The source stays the only copy of the source.

## Why

- One idea, the command, replaces source, protocol, contract, hook, adapter and registry.
- Nothing stored can't go stale, leak, or need a migration. The source's own access rules (a revoked token, a
  folder the user unselected) apply on the next read, with no copy left behind.
- Adding a source means adding two subcommands to its CLI. Auditing it means running them.

## Consequences

- #3228 is re-shaped. The `Source` protocol, `MODULES` registry, snapshot stores and `source_versions` are dropped.
  What stays is generic: on/off and consent, the cursor, failure isolation, matching items to pages for every night
  stage, and opening citations through `show`.
- Source PRs keep their CLI and add `changes`/`show --json`. Adapter modules and stores are removed.
- A cited item that was edited shows its current text, marked as changed. This is accepted.
- After the merges, audit every source on a fresh `co init` (#3249): it is detected and listed, the two commands
  answer, each night stage's material contains its items, pages cite them, and citations open live. These checks
  become `co rem sources audit`.
