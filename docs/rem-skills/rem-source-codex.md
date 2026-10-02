# Why rem-source-codex says what it says

The rules live in `connectonion/useful_skills/rem-source-codex/SKILL.md`,
appended to a stage's instructions whenever the material comes from Codex. This
file holds the measurements and incidents behind them; it is not loaded at
runtime (#1851).

## Why a batch is so small

The importer reads native CLI and Desktop user-input shapes. Early CLI rows
have `{role, type, content}`; modern Desktop rows also carry passthrough metadata
and optionally an id. `user.*` content kinds establish typed parts, while named
client-context kinds stay excluded. Older native Desktop/vscode and interactive
CLI turns can carry only `turn_id`; these are read with injected text and
scheduled `Automation:` prompts excluded. Bare imported Desktop history and
subagents remain excluded.

A native Desktop voice wrapper is read only when it has the observed explicit
`input` followed by a mixed `transcript_delta`. Only input is kept, with an
`input_scope` stating transcription/recognition limits. Tail-flush summaries,
unknown wrappers and parent-assigned worker input are excluded. An old Desktop
turn's missing content kinds are also preserved as input scope. This metadata
survives project storage, prompts and searchable evidence. Skill-mention caches
are recounted after the parser change (version 4).

The original narrow CLI filter was based on one week in September: 2,062
user-slot messages, 1,493 harness messages, with most characters in injected
context. That measurement did not establish that every metadata-bearing input
was machinery. Inspection of older native Desktop records found direct setup
and lookup requests mixed with injected blocks; voice wrappers also held explicit
requests. Language frequency alone cannot determine authorship. A small batch
is still normal, but skipped input shapes need provenance review rather than
being called proof that no user request exists.

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
