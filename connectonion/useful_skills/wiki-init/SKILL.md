---
name: wiki-init
description: The first run of a notebook. Connect the sources, enumerate what they already list, build every page with its structure in place, rank who and what matters, and investigate the most important subject first — the account's owner. Drives `co wiki` and the mail CLIs; does the programmatic steps by command and the judgement steps itself.
tools:
  - bash
---

# Initialise the notebook

You are building the frame once. Everything programmatic is a command; you
supply the judgement between the commands. Do not reimplement in prose what a
command already does.

## 1. Connect the sources

```
co outlook inbox -n 1          # authorised?  if not: co auth microsoft
co gmail inbox -n 1            # authorised?  if not: co auth google
co wiki subscriptions          # codex / claude-code roots exist? they need no auth
```

An account that is not authorised is opened in the browser for the user; you
do not enter credentials. Coding sessions are local and simply read.

## 2. Enumerate — no model, all of it

```
co wiki --json scan projects --days 150
co wiki --json scan people   --days 150 --min-mails 3 --mine <every address that is the user's>
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

For every person and project you kept:

```
co wiki stub person  "<Name>"  --email <address> --handle <name> --handle <address> --handle <any other spelling>
co wiki stub project "<Name>"  --path <cwd> --path <every worktree of it>
```

The page is created with every section present and every unknown one marked
`Unknown — not investigated yet`, and its own `Investigation:` line at the
foot. Structure is now a fact on disk, not a request in a prompt.

## 5. Investigate the owner first — from what they wrote, not what mentions them

The owner's address is on every mail in the mailbox, so searching by their
handles gathers the whole mailbox and nothing about them in particular. Their
page is built from the other direction: what they said in sessions, what they
sent and to whom, which projects they ran. Give `investigate` the owner's
*names* as handles but **not their addresses**, and expect the budget line in
the coverage — the newest material is kept and the rest waits.

The first subject is **the person whose account this is** — the sender of the
mail, the author of the sessions. Their page anchors everything else: every
other person's relationship is a relationship to them.

```
co wiki stub person "<Owner>" --email <each of their addresses> --handle <their names>
co wiki investigate people/<owner>.md
```

Then the highest-ranked project, then people in rank order, **within budget**:
read `co wiki status` for today's usage before each one and stop when the
first-run budget (2% of the Codex weekly pool, or the configured amount) is
reached. A run that stops with three people done and a ranking written down
has done its job; the daily run continues from `co wiki unfinished`.

## 6. Report

End with: how many correspondents and projects were found, how many pages were
built, who was investigated and how much it cost, what was dropped and why,
and the first three entries of `co wiki unfinished` — that is tomorrow's work.
