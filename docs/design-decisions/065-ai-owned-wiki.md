# DD-065: The AI owns the notebook; the wrapper owns execution

**Status:** Product direction accepted; implementation and native-runtime
isolation still under verification. Not a release announcement.

**Date:** 2026-09-07

**Related:** [Issue #1443](https://github.com/openonion/connectonion/issues/1443)

## Problem

A second summary after every conversation does not necessarily improve memory.
It can duplicate an old decision, hide a correction, or strip away the reason
that made the original useful. Requiring a human to maintain those summaries
would recreate the note-taking work this product is intended to remove.

We need a small way for the user's existing AI to maintain its current
understanding, and evidence that successive maintenance passes improve it.

## Product decisions

- Markdown is the canonical notebook. No SQLite, vector database, or notebook
  Git/GitHub history is required. This repository's PR is product code, not a
  proposal to version users' notebooks.
- The AI is the only supported notebook writer. Humans ask, add information,
  and correct it through their existing assistant; no note editor or semantic
  review/approve/reject workflow is introduced.
- Product-provided `wiki-maintain` and `wiki-use` Skills live in
  `connectonion/useful_skills/`. Learned procedures in
  `wiki/skills/candidates/` are inert data, not new executable instructions.
- Organization, updating, and compression are one prompt-design problem.
  Software does not decide fact promotion, merge semantics, or retention.
- The initial map remains People, Projects, Skills, Knowledge, Opportunities,
  Decisions, Principles, Works, Agenda, plus permanent general Notes.
- Start with the Codex source and Codex + Spark runner on macOS. Native client
  authentication is used; there is no implicit API-key billing fallback.
- Daily schedule times are **03:00, 04:00, 06:00, 17:00, 18:00, 19:00**, in the
  user's saved IANA timezone. No input means no automatic inference.

## Alternatives for the maintenance boundary

| Approach | Benefit | Cost / reason not selected |
|---|---|---|
| Native workspace-write plus arbitrary shell tools | Reuses a coding-agent workflow directly | Working directory is not a read whitelist; inherited MCP, Hooks, Skills, and shell access can escape the intended notebook scope. |
| AI returns structured semantic change proposals; application merges them | Centralized change interpretation | Reintroduces the schema, merge engine, and state transitions the product explicitly rejected. |
| Native Codex with only scoped Markdown file tools | AI freely reads, writes, merges and removes pages; software enforces file scope | Requires native protocol/tool-exposure verification. This is the selected implementation candidate. |

`wiki_write` is an immediate file operation, not a proposal for a second AI or
semantic engine. File deletion is limited to synthesized Markdown inside the
authorized notebook. Original sessions, runtime state, credentials, and installed
Skills are outside that authority. Individual replacements are atomic; a batch
is not a transaction and there is no rollback promise after partial writes.

## Native-runtime release gate

The initial adapter targets the locally inspected Codex CLI 0.147.x protocol.
Schema generation proves parameter shape, not enforcement. The candidate uses
an ephemeral thread, no attached execution environments, read-only native
sandbox, denied approvals, explicit model/provider, and scoped dynamic tools.
It requests disabled optional features/MCP/Hooks and no project instructions,
then checks effective configuration before a model turn. User credentials stay
with the native client. These requests are not proof of isolation.

The 0.147.0 probe found that an empty MCP map override retains inherited servers.
The chosen answer is not to override but to remove the source: the runner gives
Codex a temporary `CODEX_HOME` containing only the login file, so there is no
config.toml, plugin, hook or AGENTS.md to inherit. The effective-config check
stays as the gate that this remains true. See the
[recorded evidence](../testing/wiki-acceptance.md); the hostile-source and
successive-update tests passed against real Codex on 2026-09-07.

Before enabling real user ingestion, a synthetic native acceptance test must
demonstrate that shell execution, arbitrary reads, outside writes, external
actions, inherited instructions, and candidate-Skill execution are unavailable.
Checking a requested config value or asserting it in a mock is insufficient.
Unknown runtime/model/auth behavior must fail closed without a fallback.
Until this evidence exists, the PR remains a draft and must not be presented as
an unattended production organizer.

## Input progress is not memory state

The importer reads bounded, authorized Codex rollout messages. It preserves
speaker, timestamp, source link, and project context. System/developer
instructions, tool payloads and duplicate event-message mirrors are not treated
as user-authored notes. The organizer's own sessions are excluded.

The current adapter's date/project filters select messages sent to maintenance;
they are not a guarantee that older or other-project bytes are never opened
locally. It reads each changed rollout (up to 16 MB) within the explicitly
authorized session directory to inspect metadata and verify the consumed prefix.
First-start consent must describe that scope honestly; narrower file-level
access requires additional importer work before being promised.

Small operational files remember source choices, consumed input, and attempts.
Complete input is acknowledged only after a successful maintenance pass. An
unfinished JSONL tail is not consumed. A failure or interruption may leave valid
partial notebook writes; retain the previous input checkpoint so the Skill can
revisit the material. A rewritten consumed source prefix must be reported,
not silently mistaken for an append or erased by resetting progress.

Progress files and locks do not describe semantic states such as “principle
promoted” or “decision superseded.” Those distinctions belong in ordinary prose
and Skill judgment.

## Milestone boundary and CLI consistency

Milestone 1 proves the foreground session → maintenance → Markdown → retrieval
loop and honest logs. It is a building block of the background product.
`co wiki start` must retain its agreed meaning: prepare missing setup, confirm
access once, and start background organization. **Do not ship a command called
`start` that silently means “run once in the foreground.”** The background
worker/login wrapper and HTML reader are subsequent work; any command depending
on them remains explicitly unshipped until it works.

The background lifecycle is the OS scheduler, not a worker of ours. `start`
writes one per-user launchd job that runs `co wiki sync` at the six times and
once at login; `sync` carries the lock, the attempt cap and the checkpoint, so
there is one implementation of the logic and one declarative file per OS. A
process of our own would still need a per-OS login launcher and would sit on
top of it. Other platforms get consent and manual `sync` until their job file
exists. The consent summary is shown before any body is read, and a
noninteractive first start refuses rather than consenting silently.

Default Claude Code and authenticated email subscriptions remain the product
policy. Implementing only the Codex adapter first must not display the others
as working collectors. Manual unsubscribe remains durable when adapters arrive.

## Defaults that are not newly approved

The seven-day initial backfill, six-attempt daily cap, absolute root
`~/.co/wiki`, batch sizes, timeout, and login preference are proposals. Preview
code may expose them as inspectable defaults; that does not authorize collection.
First-run consent must show the actual effective values and source scopes.
The six-attempt cap includes initial/manual/retry attempts and can prevent a
later scheduled invocation; it is neither six guaranteed model calls nor a
Token/billing ceiling. Do not silently raise it.

## Evidence required

See [Wiki acceptance tests](../testing/wiki-acceptance.md). Tests and user-facing
contracts precede additional implementation. Each claimed behavior needs
observable evidence; a mock that hardcodes a good note does not validate the
maintenance Skill's reasoning. No release is claimed by this document.
