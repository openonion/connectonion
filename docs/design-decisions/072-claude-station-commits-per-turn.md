# DD072 — Claude Station commits once per turn

Status: fix for #1654, targeting the 1.8.8 preview after b5.

## The rule

A Host session is committed **once per turn**. `SessionStorage` appends a
whole-session record on every commit and the last line wins, so the cost of a
commit is the size of the session. Every other Host writer follows this rule:
a normal agent turn, and `provider_workroom` for a browser-driven Claude or
Codex turn, write once when the turn ends.

Claude Station (`co claude`, #1630) committed once per Hook event. A tool call
is two events, so a session of N tool calls wrote N whole-session copies: 1,000
tool calls produced a 769 MB `session_results.jsonl`, and each commit took
longer than the one before.

## What Station does now

| Step | Writes to disk? |
|---|---|
| Hook fact or transcript message → `_append` | No. It is buffered in `_pending` |
| `Stop` (terminal turn ended) → `_commit` | Yes, one record with all of the turn's events |
| Control change (`_transition`: start, take, release, exit, failure) → `_commit` | Yes, one record |

`events_since(offset)` returns the committed trace plus `_pending` under the
station lock. The Work Room watcher reads through it, so a paired browser
still sees every tool call live. The wire protocol does not change.

Durable readers only read at commit points: `take_control`, `release_control`
and `provider_workroom._provider_source`, which needs the terminal
`provider_invocation` with status `completed`. Every commit point comes before
those reads.

## Hook receiver limits

- The total cap of 4,096 Hook events per terminal run is deleted. Once a long
  session hit it, the mirror stopped silently and every approval after that
  was refused.
- The 128-per-second rate limit still bounds observation. It no longer applies
  to `PermissionRequest`, so an approval is never shed because Claude was busy
  in the same second.

## Measured

This is the #1654 reproduction with 10 tool calls per turn:

| tool calls | before | after |
|---|---|---|
| 250 | 48.6 MB | 2.8 MB |
| 500 | 193.0 MB | 11.0 MB |
| 1,000 | 768.9 MB | 43.3 MB |

## Trade-offs

- **Mid-turn crash:** the activity cards of the unfinished turn are not
  persisted. The normal Host behaves the same way, and Claude's own transcript
  still has the whole turn.
- **Still quadratic in turns.** Committing per turn fixes the per-event
  multiplier, not the storage shape: every Host session has the same curve
  across turns, and `compact()` at startup reclaims the superseded records.
  Making it linear means an append-only event log with sequence numbers, as
  Happy Coder's server does, and that belongs in `SessionStorage` for all Host
  sessions, not in Station. It is tracked in #1659 rather than solved here
  with a second persistence format.
