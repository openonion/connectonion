# Why wiki-source-codex says what it says

The rules live in `connectonion/useful_skills/wiki-source-codex/SKILL.md`,
appended to a stage's instructions whenever the material comes from Codex. This
file holds the measurements and incidents behind them; it is not loaded at
runtime (#1851).

## Why a batch is so small

The filter on a line is: `type == "response_item"`, `payload.type ==
"message"`, `payload.role == "user"`, and payload keys exactly
`{role, type, content}`. That last condition is the whole game. It is enforced
before the batch reaches the model.

**97% of what Codex files under `role: user` was never typed by the user.**
Measured over one week, 2026-09-12: 2062 `role: user` messages, of which 1493
were the harness talking to itself — 19.1M characters of machinery against
0.55M of person. Codex writes AGENTS.md, the approval reviewer's replayed agent
transcript, and injected goals into the *user* slot. The structural tell is a
fourth key, `internal_chat_message_metadata_passthrough`: a real person's
message carries only `role`, `type` and `content`.

So a batch of 40 items is 40 things the user actually typed, not 40 log lines.

## How the store is laid out

- Dated directories, oldest first, so a backfill walks the timeline forward.
- Progress is per file: a byte offset plus a digest of the consumed prefix, so
  an appended session resumes and a rewritten one is refused.
- The model has repeatedly read the `cwd` **directory name as the project
  name**; the notebook's own page title wins.
- **Codex does not delete sessions.** Upstream retains them indefinitely
  (openai/codex#6015 is still a request). On this account the store begins
  2026-08-17 on the new laptop and 2024-12-04 on the previous one, so a gap
  means the machine changed.
- Rollout files of 426 MB have been seen.

## What this source has taught us

Each rule produced a bad page before it was written down.

- **Intent, not repository state.** The assistant's execution is not in the
  batch at all. Git SHAs, CI run counts, PR numbers and screenshot paths were
  filling pages until this was measured, and they were mostly coming from the
  injected machinery, not from the user.
- **One session is one sitting.** Six batches over 119 items produced four
  pages describing the same state, because each session was treated as a new
  project.
- **A Sources line is not a receipt.** The model piled a dozen ids onto one
  page.
- **Pasted material** (a stack trace, a log, a file) is evidence for what the
  user was doing, not something they said.
- **A question is not a decision.** "should we use X?" and "we're using X" read
  alike in a bullet and mean opposite things.
- **Skills and slash commands are instructions to the tool**, not beliefs the
  user holds.
