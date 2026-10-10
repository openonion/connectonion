---
name: rem-source-codex
description: Where the user's own words are inside Codex CLI sessions, how that store is laid out, and what this source has already taught us. Loaded alongside whichever stage Skill is running when the material comes from Codex.
---

# Codex CLI as a source

Why these rules: docs/rem-skills/rem-source-codex.md

Read with the stage Skill that loaded it (`rem-extract`, `rem-maintain` or
`rem-investigate`): that one says what to produce, this one what is true of
this source.

## Where the user's words are

`~/.codex/sessions/YYYY/MM/DD/rollout-<ISO>-<uuid>.jsonl`, one JSONL file per
session. The importer recognizes native CLI and Desktop user-input shapes;
harness context, imported history, subagents and scheduled automation prompts
are excluded. An `input_scope` may identify an older Desktop turn without client
content kinds, or an explicit voice transcription with the mixed transcript
omitted. Preserve those limits: transcribed wording can contain recognition
errors. `timestamp_scope` marks legacy session-start dates. A session folder
is context, not proof of the product's identity.

## The store

- Directories are dated, oldest first. `cwd` in the session header is the
  project, but the notebook's page title wins over the directory name.
- A gap in the timeline means a machine change, not expired history.
- Sessions can be hundreds of MB; never assume one fits.

## Rules

- **A session records intent, not repository state.** Write "decided to X
  because Y", never git SHAs, CI run counts, PR numbers or screenshot paths.
- **One session is one sitting, not one project.** Same-day sessions usually
  continue one thread; do not open a page per session.
- **Sources: keep the few ids that carry the claim**, not every id seen.
- **Pasted material is not the user's words.** Summarise why a trace, log or
  file was pasted; do not quote it back.
- **A question is not a decision.** Keep the mood ("should we use X?" vs "we're
  using X").
- **A bare `/skill args` message records that the user ran something**, not a
  belief. Note it only when running it is itself the fact.

## What a Codex note looks like

```
## Decisions
- Decided co rem runner keeps Codex isolated by giving it a temporary
  CODEX_HOME containing only auth.json, after finding that `-c mcp_servers={}`
  leaves inherited servers enabled. — user, 2026-09-07, codex:s1:412

## Projects
- connectonion: spent the week on co rem feature; the open question at the
  end of the batch is whether background maintenance ships on launchd or a
  worker of our own. — user, 2026-09-07, codex:s1:88, codex:s1:640

## Agenda
- Promised to check the extraction prompt against a real 60-day mailbox before
  raising the batch size again. — user, 2026-09-08, codex:s2:210
```
