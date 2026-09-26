# Scheduled work: `.co/schedule.yaml` and `co schedule`

An agent can do work on its own clock: a report every Monday at 9, a sync
every 15 minutes. You write the schedule in `.co/schedule.yaml`; the hosted
agent (the script that calls `host(...)`, locally or after `co deploy`) runs it; `co schedule` shows it and
lets you run, pause or resume an entry.

The clock lives inside the agent process, so it works the same on macOS,
Windows and Linux with no cron or systemd setup (#521).

## Quick start

```yaml
# .co/schedule.yaml
- name: morning report
  at: "Mon 09:00"
  tz: Australia/Sydney
  run: "Summarise last week's orders and email the team"

- name: sync
  every: 15m
  exec: "python scripts/sync.py"
```

```bash
co schedule check        # does the scheduler read it the way you meant?
co schedule              # what runs next, what ran last, how it went
```

Start the hosted agent (`python agent.py` when it calls `host(...)`, or
`co deploy`) and the entries run from then on.

## Entry fields

| field | meaning |
|---|---|
| `name` | How the entry is shown and addressed (`co schedule run <name>`). Defaults to the `run` or `exec` text. Must be unique. |
| `run` | A prompt. It runs as an agent turn through the same path as a message sent to the agent, and lands in `.co/session_results.jsonl` like any other session. |
| `exec` | A shell command, run in the project directory. Recorded by exit code, with the end of stderr kept on failure. Use it for deterministic work: a model's "I ran the script" is not evidence the script ran (#709). Limited to 10 minutes. |
| `every` | An interval: `30s`, `15m`, `2h`, `1d`. Must be greater than zero. |
| `at` | A time: `"09:00"` (daily) or `"Mon 09:00"` (weekly). |
| `tz` | IANA timezone for `at`, e.g. `Australia/Sydney`. Defaults to UTC. |

Each entry needs exactly one of `run` or `exec`, and one of `every` or `at`.

## How it runs

- **One tick a minute.** Each minute the agent finds the due entries, marks
  each one `running` in `.co/schedule-state.json`, and runs each as its own
  task. A slow entry never delays another one.
- **One copy at a time.** An entry still running when it comes due again is
  skipped, and the log says so. An entry that overruns every time is
  configured with the wrong interval.
- **Catch-up, once.** A run missed while the agent was down fires on the next
  tick, once, however many were missed. A new `at` entry does not back-fill
  earlier occurrences from before it existed.
- **One scheduler per cluster.** Under `--workers N`, one worker claims each
  tick, so an entry is not started N times.
- **Edits apply live.** The file is re-read every tick. An entry the agent
  writes into `schedule.yaml` while running starts without a restart.
- **A bad entry is dropped, not fatal.** It is reported at startup and by
  `co schedule check`; the other entries keep running.

## Seeing and controlling it: `co schedule`

| command | what it does | writes |
|---|---|---|
| `co schedule` / `co schedule list` | each entry: cadence, next run, last run, status, failure reason, session id, paused. `--json` for scripts. | nothing |
| `co schedule check` | validate `schedule.yaml` exactly as the scheduler reads it; exit 1 naming each ignored entry | nothing |
| `co schedule run <name>` | run the entry on the next tick, even if it is paused or not due | schedule state |
| `co schedule pause <name>` | stop the entry firing | schedule state |
| `co schedule resume <name>` | put it back on its schedule | schedule state |

`run`, `pause` and `resume` write `.co/schedule-state.json`, never
`schedule.yaml`. The state file belongs to the machine the agent runs on and
is not deployed over, so a pause survives restarts and deploys. The running
agent acts on it at its next tick, within a minute. Run the commands in the
agent's project directory, on the machine where it runs.

The agent's Home page shows the same state in its **Scheduled** section:
running, paused, when it last ran, and why a run failed.

## Where results go

| file | holds |
|---|---|
| `.co/schedule-state.json` | per entry: last run, status (`running`, `done`, `failed`), failure reason, session id, `paused` |
| `.co/session_results.jsonl` | the full session of each `run` entry: prompt, transcript, result, duration. Over HTTP, `GET /sessions` shows these to the agent's admins only: nobody signed for them, so they belong to the agent. |

`done` means the turn returned, not that the work succeeded: a model that
answered "I could not reach the drive" also returned. Check the session, or
use `exec` when success is a fact a command can report.

If the agent stops while an entry is running, the next start records that run
as `failed` with the reason "the agent stopped during this run".
