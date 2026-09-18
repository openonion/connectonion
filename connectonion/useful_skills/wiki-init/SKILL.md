---
name: wiki-init
description: The first run of a notebook. Connect the sources, enumerate what they already list, build every page with its structure in place, rank who and what matters, and investigate the most important subject first — the account's owner. Drives `co wiki` and the mail CLIs; does the programmatic steps by command and the judgement steps itself.
---

# Initialise the notebook

You are building the frame once. Everything programmatic is a command; you
supply the judgement between the commands. Do not reimplement in prose what a
command already does. The task supplies the notebook root: include
`co wiki --root "<root>"` in EVERY Wiki command below, including follow-ups.
Read existing pages and `co wiki people` before creating another identity.
Do not call `co wiki init` recursively or install a background schedule here.

## 1. Connect the sources

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

## 5. Investigate the owner first — from what they wrote, not what mentions them

The owner's address is on every mail in the mailbox, so searching by their
handles can gather the whole mailbox. Keep their names and addresses on the
page: the command reads those handles back automatically. Build their profile
from what they said in sessions, what they sent and to whom, and which projects
they ran. Being the recipient of a notice does not establish a personal fact.

When the gathered material exceeds one input, `investigate` summarises it in
bounded chunks, oldest first, then supplies the digests and existing page to
the writing pass. Long attachments are split too. Check the coverage and
per-stage usage; do not claim that the oldest material was discarded or that
one investigation necessarily costs one model call.

The first subject is **the person whose account this is** — the sender of the
mail, the author of the sessions. Their page anchors everything else: every
other person's relationship is a relationship to them.

```
co wiki stub person "<Owner>" --email <primary-address> --handle <other-address> --handle <their-name>
co wiki investigate people/<owner>.md
```

Stop after the owner's first investigation and the ranked map unless the user
explicitly requested more subjects. Do not invent a monetary or subscription
meter: `co wiki status` reports attempts and known tokens, not percent of the
Codex weekly pool. A 2% / 1% / dollar budget requires an actual provider meter;
if it is unavailable, report that it was not enforced. Never infer a percentage
from tokens. Record where to continue with `co wiki unfinished`.

## 6. Report

End with: how many correspondents and projects were found, how many pages were
built, who was investigated and how much it cost, what was dropped and why,
and the first three entries of `co wiki unfinished` — that is tomorrow's work.
