# Personal Wiki — milestone 1 contract

**Unshipped design / PR work, 2026-09-07.** The current release has no
`co wiki` group. The examples below define the acceptance contract; they are
not installation instructions for a released feature.

## Implemented on the draft branch

The branch now covers the whole milestone-1 loop on macOS: confirm sources once,
maintain in the background through launchd, inspect, open, stop.

```bash
co wiki start
co wiki start --yes
co wiki stop
co wiki sync
co wiki sync --source codex
co wiki sync --dry-run
co wiki subscribe codex --project /path/to/project --since 30d
co wiki unsubscribe codex
co wiki
co wiki status
co wiki subscriptions
co wiki config
co wiki config set model gpt-5.6-luna
co wiki list people
co wiki show people/alice.md
co wiki search "Alice" --type people
co wiki logs
co wiki open
co wiki open --no-launch
co wiki doctor
```

`start` prints the consent summary (exact session directory, lookback, model and
where messages go, timezone and the six slots, limits, what the background job
is) and asks once. In a pipe it refuses and asks for `--yes` after the summary
has been read; it never consents silently. On the first confirmed start it runs
the first bounded batch in the foreground so there is something to look at
immediately, then installs a per-user launchd job that runs
`co wiki sync --scheduled` every five minutes. That tick checks, in the saved
timezone, whether one of the six times has come due since the last scheduled
batch: if so it runs one batch, otherwise it exits at once without touching the
notebook. Slots missed while asleep or powered off collapse into one catch-up at
the first tick after wake. (launchd's own calendar triggers were measured not to
fire on macOS 26; the interval tick fires to the second.) Repeating `start`
re-applies the schedule without asking again or repeating the first batch.
`stop` removes the job and records it; consent, notes and manual `sync` remain.
Background scheduling is macOS-only in this milestone; elsewhere `start` records
consent and tells you to run `sync` yourself.

`open` renders the whole notebook into one self-contained HTML file under the
system temporary directory (mode 0600, named after the notebook root) and opens
it in the default browser; `--no-launch` only writes it and prints the path. The
page is a snapshot with an "as of" time — a page opened from `file://` cannot
read the Markdown beside it, so the notes are embedded at render time. Run
`open` again after the next maintenance pass. It never writes inside the
notebook and never starts a model.

Place group options before the command, for example
`co wiki --root /path/to/wiki --json status`. Read commands never initialize a
notebook; `config set` writes settings only, not content or a background job.
Malformed configuration must produce a nonzero diagnostic without rewriting the
file. `config` can still display the original mapping for diagnosis.

The commands below are the **target contract**, including unfinished commands;
the branch's `co wiki --help` lists only the implemented subset above.

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

Default-subscribe to Codex and Claude Code — both are read on this branch, from
`~/.codex/sessions` and `~/.claude/projects` respectively, oldest session first
so the notebook grows the way the user's understanding did. Enable Gmail/Outlook
only when the corresponding adapter exists and existing co authentication has
read access. No login flow or newly discovered account is silently added. The
default lookback is 60 days; a custom scope may ask for at most 180 days of
coding sessions and 730 days of mail. `sync --all` is the backfill: batch after
batch until nothing is pending, not subject to the daily attempt cap because the
user asked for it.

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

There is no worker process of ours: launchd wakes `sync --scheduled` every five
minutes and `sync` owns the decision — the saved times, the saved timezone, the
lock, the attempt cap and the checkpoint. A tick that arrives while a batch is
still running is refused as busy and the slot stays owed for the next tick.

## Two passes for large batches

A sync gathers up to `limits.extract_items_per_batch` (150) messages. When more
than `limits.items_per_batch` (20) arrive, the batch first goes through the
`wiki-extract` Skill: one native turn with no tools whose whole reply is the
extraction notes — every durable fact with who said it, the date and its
source ids, grouped by kind, routine tool chatter dropped. `wiki-maintain` then
reads that one digest instead of the raw messages. A batch that fits
`items_per_batch` skips extraction. Both turns count against the daily attempt
cap; the run record says `extracted: true` and sums the usage. Measured on a
120-message session: one extraction plus one maintain turn, 68k tokens, 31 s,
against five maintain batches and roughly four times the tokens without it.

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

Host/OIP/remote access, Notion/cloud sync, sharing, human editing,
review/approve/reject, generated-Skill installation, and template management are
not part of this first slice. The bundled reader template is a client of one
embedded data object; serving that object over HTTP later is how it would become
a site, without a second renderer.

The agreed file layout and implementation reasoning are in
[DD-065](../design-decisions/065-ai-owned-wiki.md).
