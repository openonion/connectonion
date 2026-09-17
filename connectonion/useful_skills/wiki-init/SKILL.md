---
name: wiki-init
description: The first run of a notebook. Map installed skills, people and projects with page skeletons, connect sources, rank what matters, and leave an investigation queue. Drives co wiki and the mail CLIs.
---

# Initialise the notebook

You are building the frame once. Everything programmatic is a command; you
supply the judgement between the commands. Do not reimplement in prose what a
command already does. The task supplies the notebook root: include
`co wiki --root "<root>"` in EVERY Wiki command below, including follow-ups.
Read existing pages and `co wiki people` before creating another identity.
Do not call `co wiki init` recursively or install a background schedule here.

Before using the source CLIs, read [CLI.md](CLI.md), beside this file. It gives
the exact mail, browser and Wiki command forms, ID handling, pagination and
failure recovery. Resolve that path from this Skill's directory, not the task's
working directory. Run commands through the shell tool; do not invent tool names
or assume that Gmail, Outlook and `co email` share an inbox or query syntax.
Use the supplied absolute notebook root in every Wiki command; examples below
abbreviate it for readability. Replace placeholders with observed values.

## 1. Map installed skills, then connect the sources

`co wiki init` has already created the installed-Skill map before starting this
model stage. Read `skills/catalog/index.md` and keep its existing pages. When
invoked directly as `/wiki-init`, build that map first:

```bash
co wiki --root '<absolute-notebook-root>' map-skills
```

This deterministic command scans known co/Claude/agent/Codex skill directories
and co ai's bundled defaults. It writes a generated index and one inert Markdown
skeleton per distinct source under `skills/catalog/`. Names, descriptions and
source paths come from metadata; usage, inputs/outputs, related projects and
history remain Unknown until supported. It never copies executable `SKILL.md`
files into the notebook or activates them. Same-name skills from different files
remain distinct; symlink aliases to the same source are one page. Reruns preserve
existing page content and do not delete notes for missing sources.

Check the index's coverage: this is not a recursive scan of every plugin cache or
remote catalog. To inventory a known additional root, run `map-skills --skills-dir
'<actual-skill-directory>'` (repeat the flag for multiple roots); explicit roots
replace the default scan. Never guess a directory from a model-generated path.
The index describes the latest scan; existing pages remain available via `list skills`.

Directory responsibilities:

| Directory | What belongs here |
|---|---|
| `people/` | Person pages and their relationships, sources and open threads |
| `projects/` | Project pages: purpose, status, architecture and open threads |
| `skills/catalog/` | Map and expandable documentation of installed skills |
| `skills/candidates/` | New reusable procedures learned from work; inert proposals |
| `skills/approved/` | Reserved; Wiki cannot write executable/approved skills |
| `knowledge/`, `decisions/`, `principles/` | Supported knowledge and later abstractions; do not invent entries to fill folders |
| `works/` | Descriptions and locations of reusable artifacts |
| `notes/` | Init ranking, coverage gaps and other supported notes |
| `.state/` | Runner-owned progress and task files; never hand-edit as Wiki content |

`agenda/` and `opportunities/` exist for compatibility, but investigation and
abstraction derive these views from entity state rather than duplicate entries.
A Codex task's `outputs/` is its delivery directory, not automatically the Wiki
root. Keep one authoritative notebook; label any copies exported to `outputs/`.

```
co outlook inbox -n 1          # authorised?  if not: co auth microsoft
co gmail inbox -n 1            # authorised?  if not: co auth google
co wiki subscriptions          # codex / claude-code roots exist? they need no auth
co email addresses             # the account\'s own mail service; if not ready: co auth
```

An account that is not authorised is opened in the browser for the user; you
do not enter credentials. Coding sessions are local and simply read.

## 2. Enumerate — no model, all of it

```
co wiki --json scan projects --days 150
co wiki --json scan people   --days 150 --min-mails 1 --mine <every address that is the user's>
```

`--mine` takes every address the user sends from, across all mailboxes,
including private ones — the user's own private Gmail turned up as the third
most active "correspondent" when it was left out.

## 3. Judge — this is your part

**Projects.** Collapse to repositories: entries with the same `repo` or
`origin` are one project, and an `is_worktree` path is not a project of its
own. Drop the workspace root (a parent directory of many repositories: 711
sessions, no `.git`) and anything under a temp or scratch path. Rank what is
left by sessions and recency.

**People.** Each correspondent is one of: a person; a company's own notices
(billing, product, account — still that company talking to us); event
promotion or a call for applications (a lead); or transactional noise
(receipts, one-time codes, unread newsletters). `automated_hint` and `one_way`
are signals, not verdicts — an MBB notice and a courier receipt both trip
them, and only one belongs in the notebook. Persons and companies get a page;
leads are noted for the opportunities view; noise is dropped.

Rank people by: mails, both directions (`one_way` false), recency, and whether
their subjects name a project you just ranked.

**Write the ranking down** as `notes/init-<date>.md`: who was ranked where and
why, what was dropped and why. The next run reads it before re-judging.

## 4. Build the frame

Ask the mail which organisations are real before stubbing people, because a
person's `Company` should link to a page where one exists:

```
co wiki scan orgs --days <same window>
```

It lists only work domains two or more people write from — the point at which
institutional facts would otherwise be copied onto every one of their pages.
It proposes; you judge. Add a one-person domain yourself when something was
agreed with the entity rather than the person (a signed contract, recurring
money, a programme that outlives this contact). A mailbox provider is never an
organisation.

For every person, organisation and project you kept:

```
co wiki stub person  "<Name>"  --email <address> --handle <name> --handle <address> --handle <any other spelling>
co wiki stub org     "<Name>"  --domain <domain> --domain <any other domain> --person people/<slug>.md
co wiki stub project "<Name>"  --path <cwd> --path <every worktree of it>
```

The page is created with every section present and every unknown one marked
`Unknown — not investigated yet`, and its own `Investigation:` line at the
foot. Structure is now a fact on disk, not a request in a prompt.
Before leaving the map stage, read a representative message/signature for each
kept person using the mail CLI. Fill already-supported phone, company, role
and address fields now, with references; unknown fields remain unknown.
The person page template is the single canonical `wiki-page-person` Skill.
Reuse an existing page when address, aliases and context identify the same person.

## 5. Hand off to investigation

Init ends with the map. Create the account owner's skeleton and verified
address aliases, but do not call `co wiki investigate` during init. List the
owner first in the suggested investigation queue. Investigate is a separate,
explicit follow-up which reads evidence and fills the same page structure.
A mapped page is not an investigated page.

People follow `wiki-page-person`; projects follow `wiki-page-project`; installed
skill documentation follows `wiki-page-skill`. The runner appends these page
Skills. For direct `/wiki-init` use, read their sibling `SKILL.md` files before
writing. Preserve existing pages, exact headings and runner-owned status lines.

## 6. Report

End with: how many installed skills, correspondents and projects were found, how many pages were
built, what remains uninvestigated, mapping usage, what was dropped and why,
and the first three entries of `co wiki unfinished` — that is tomorrow's work.
