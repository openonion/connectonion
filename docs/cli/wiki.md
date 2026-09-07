# Personal Wiki — milestone 1 contract

**Unshipped design / PR work, 2026-09-07.** The current release has no
`co wiki` group. The examples below define the acceptance contract; they are
not installation instructions for a released feature.

Wiki is a notebook maintained by your AI from authorized sessions. Ask your
existing assistant to retrieve it, remember something, or correct a note.
You do not need to edit Markdown or audit a queue of proposed changes.

## Core command contract

One command per line; do not add commands merely to meet a target count.

```bash
co wiki start
co wiki stop
co wiki
co wiki status
co wiki subscriptions
co wiki subscribe codex
co wiki subscribe codex --project /path/to/project --since 30d
co wiki unsubscribe codex
co wiki config
co wiki config set model gpt-5.6-luna
co wiki config set schedule.times "03:00,04:00,06:00,17:00,18:00,19:00"
co wiki config set schedule.timezone Australia/Sydney
co wiki sync
co wiki sync --source codex
co wiki sync --dry-run
co wiki list people
co wiki list skills
co wiki show people/alice.md
co wiki search "Alice"
co wiki search "storage" --type decisions
co wiki logs
co wiki logs --run run_01
co wiki doctor
```

`people/alice.md` and `run_01` illustrate values returned by list/log output;
they are not guaranteed records. Keep a selected custom Wiki root in every
follow-up command. `--help` must enumerate every implemented capability.
Do not advertise `start`, `stop`, or other future verbs as implemented before
their complete behavior is verified.

## First start

`start` creates only missing directories/settings and then starts background
work. There is no `wiki init`. Before reading source bodies, it shows one clear
confirmation containing:

- Exact session directories/project scope and initial history boundary.
- Effective runner/model and where the model receives those messages.
- The saved timezone and six daily schedule slots.
- Effective input/attempt/time limits and login-launch behavior.
- Which subscribed sources are available, waiting, or not implemented yet.

Declining must leave source bodies unread. Noninteractive first start cannot
silently consent. Repeating start must preserve notes, settings, unsubscribes,
and progress, without repeating the initial backfill. Installing the package is
not permission to collect data or launch a background job.

Default-subscribe to Codex and Claude Code; enable Gmail/Outlook only when the
corresponding adapter exists and existing co authentication has read access.
No login flow or newly discovered account is silently added. In milestone 1,
Claude Code and email adapters are explicitly deferred, not simulated.

## Running and stopping

First successful start queues one bounded batch. `sync` requests one incremental
batch now; it does not turn background scheduling on. Initial/manual/scheduled
work shares a notebook lock and the configured attempt cap. Unsubscribing stops
future reads for that scope, not the source app, account login, or retained notes.

`stop` persistently disables automatic work and stops only its owned background
batch. It must not kill another foreground sync or unrelated Codex task.
Sleeping/off computers do not run; missed slots coalesce into at most one
catch-up batch. A run is not promised at every slot when access/budget is missing
or another batch is already active.

The first implementation proves the foreground maintenance core before wiring
this background lifecycle. It must not redefine `start` as a foreground-only
alias just because the worker is not implemented yet.

## Reading and configuration

`status`, `logs`, `subscriptions`, `config`, `list`, `show`, and `search` inspect
local files without model calls or implicit setup. Before first start they show
not-started/unsaved defaults. Search initially uses literal case-insensitive
text, not semantic retrieval or a database. Skills listed from the notebook are
candidate procedure notes, not executable installed Skills.

`sync --dry-run` reports pending file metadata only: no source body reads,
model calls, checkpoint changes, or semantic diff. It must not claim an exact
pending-message count that would require opening the bodies.

Config edits validate all supplied values before replacing the file; preserve
unrelated settings. No credentials belong in `config.yaml`. Spark is the default;
Luna is an explicit choice only if the runtime/account supports it. Invalid or
unavailable choices produce a clear failure, not a different model or API bill.

## Logs must distinguish facts

Show batch outcomes separately from native runner attempts and internal model
requests. Persist actual input/output/cache counts only when returned. Unknown
is not zero, cumulative notifications are not added repeatedly, and failed-run
usage counts when known. Aggregates identify the saved timezone and coverage.
Tokens do not establish remaining account quota or the subscription bill.

No raw emails, whole sessions, credentials, or private source excerpts enter
operational logs. A partial run is not reported as completed merely because it
wrote a page. No rollback or lossless-memory promise is made.

Every implemented execution prints one concrete next command, including when
piped. JSON output carries the next command inside JSON; diagnostics go to
stderr. Failed operations return nonzero. Exit codes and examples become
operational Skill instructions only after they have been exercised.

## Deferred

The local HTML/CSS reader will use one bundled template. Host/OIP/remote access,
Notion/cloud sync, sharing, human editing, review/approve/reject, generated-Skill
installation, and template management are not part of this first slice.

The agreed file layout and implementation reasoning are in
[DD-065](../design-decisions/065-ai-owned-wiki.md).
