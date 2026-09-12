---
name: wiki-extract-codex
description: What a batch of Codex CLI sessions is, where the user's own words are in it, and what this source has already taught us. Loaded after wiki-extract when the batch comes from Codex.
---

# Extracting from Codex sessions

Read this together with `wiki-extract`, which says what a durable fact is and
how to write a bullet. This file says only what is true of **this** source.

## Where the user's words are

```
~/.codex/sessions/YYYY/MM/DD/rollout-<ISO>-<uuid>.jsonl
```

One file per session, JSONL, appended as the session runs. A line is a message
the notebook cares about only when all of this holds:

```
type    == "response_item"
payload.type == "message"
payload.role == "user"
payload keys == exactly {role, type, content}
```

That last condition is the whole game, and it is already enforced before the
batch reaches you — but you must know it, because it explains why a batch is
so much smaller than a day of work looks like.

**97% of what Codex files under `role: user` was never typed by the user.**
Measured over one week, 2026-09-12: 2062 `role: user` messages, of which 1493
were the harness talking to itself — 19.1M characters of machinery against
0.55M of person. Codex writes AGENTS.md, the approval reviewer's replayed
agent transcript, and injected goals into the *user* slot. The structural tell
is a fourth key, `internal_chat_message_metadata_passthrough`: a real person's
message carries only `role`, `type` and `content`.

So what reaches you is small on purpose. A batch of 40 items is 40 things the
user actually typed, not 40 log lines.

## How the store is laid out

- Dated directories, oldest first — a backfill walks the timeline forward.
- Progress is per file: a byte offset plus a digest of the consumed prefix, so
  an appended session resumes and a rewritten one is refused.
- `cwd` in the session header is the project. The model has repeatedly read the
  **directory name as the project name**; the notebook's own page title wins
  over whatever the path happens to be called.
- **Codex does not delete sessions.** Upstream retains them indefinitely
  (openai/codex#6015 is still a request). A gap in the timeline means the
  machine changed, not that history expired — on this account the store begins
  2026-08-17 on the new laptop and 2024-12-04 on the previous one.
- Rollout files get large: 426 MB has been seen. Never assume a session fits.

## What this source has taught us

Each line is something that produced a bad page before it was written down.

- **A coding session records intent, not repository state.** The user's message
  is what they wanted; the assistant's execution is not in this batch at all.
  So a note reads "decided to X because Y", never "the branch is at abc1234".
  Git SHAs, CI run counts, PR numbers and screenshot paths were filling pages
  until this was measured — and they were mostly coming from the injected
  machinery, not from the user.
- **One session is one sitting, not one project.** Several sessions in a day
  usually continue one thread of work; a note that treats each as a new
  project produces four pages saying the same thing. This happened: six
  batches over 119 items produced four pages describing the same state.
- **A Sources line is not a receipt.** The model piled a dozen ids onto one
  page. Keep the few that actually carry the claim.
- **Pasted material is not the user's words.** A stack trace, a log, a file
  the user pasted in is evidence for what they were doing, not something they
  said. Summarise why it was pasted; do not quote it back.
- **A question is not a decision.** "should we use X?" and "we're using X"
  read alike in a bullet and mean opposite things. Keep the mood.
- **Skills and slash commands are instructions to the tool.** A message that
  is only `/some-skill args` records that the user ran something, not that
  they believe anything. Note it only when what they ran is itself the fact
  worth keeping.

## What a Codex note looks like

```
## Decisions
- Decided the Wiki runner keeps Codex isolated by giving it a temporary
  CODEX_HOME containing only auth.json, after finding that `-c mcp_servers={}`
  leaves inherited servers enabled. — user, 2026-09-07, codex:s1:412

## Projects
- connectonion: spent the week on the Wiki feature; the open question at the
  end of the batch is whether background maintenance ships on launchd or a
  worker of our own. — user, 2026-09-07, codex:s1:88, codex:s1:640

## Agenda
- Promised to check the extraction prompt against a real 60-day mailbox before
  raising the batch size again. — user, 2026-09-08, codex:s2:210
```
