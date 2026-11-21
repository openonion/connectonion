# Asana tasks: `co asana`

Read your Asana projects, tasks and their discussion from the terminal, move a
due date, mark a task done or open, and comment, as yourself. Built on Asana's
REST API (`https://app.asana.com/api/1.0`) with a personal access token.
The agent-facing guide is the `co-asana` Skill
(`connectonion/useful_skills/co-asana/SKILL.md`).

`check`, `projects`, `tasks`, `task`, `stories`, `changes` and `show` are read-only. `update` and
`comment` print a preview and change nothing until you add `--yes`.

> Status: the examples below were produced on 2026-11-02 by the real commands
> against the synthetic workspace in `examples/co-asana-evals` (no network).
> The reads, `update` and `comment` were also run against a real workspace
> while they were built (October 2026).
> The `projects` and `tasks` rows are shown in the column layout those
> commands print since 2026-11-12; the data is the same.

## Setup

1. In Asana, open <https://app.asana.com/0/my-apps> and create a personal
   access token.
2. Save it, encrypted:

   ```bash
   co env set ASANA_ACCESS_TOKEN <pat> --secret
   ```

   An `ASANA_ACCESS_TOKEN` exported in your shell wins over the saved one.
3. Check it:

   ```text
   $ co asana check
   ✓ Asana: acting as Alex Chen <alex@atlas.example>
     Workspace: Atlas Studio  1209000000000010
   Next: co asana projects
   ```

   Bare `co asana` prints the same; `co asana --help` shows the commands.

The token acts with your permissions; comments it posts are yours, and Asana
notifies the task's followers.

## Rows, names and gids

| you give | where it comes from |
|---|---|
| a row number to `tasks` | the latest `co asana projects` list |
| a row number to `task`, `stories` | the latest `co asana tasks` list |
| a project name to `tasks` | the exact name, in quotes if it has spaces |
| `--workspace` | a name or gid from `co asana check`; needed only with several workspaces |
| `--assignee` | `me`, an email, or a user gid |
| a gid | `--ids`, `--json`, or the first line of `co asana task` |

Rows last 15 minutes and belong to the account that listed them. Each list
prints `Listing: <id>`; `--listing <id>` pins an older list. `update` and
`comment` take a task gid, or a row only together with its `--listing`. With
`--json` no rows are saved: scripts use gids.

## Read

```text
$ co asana projects
4 projects in Atlas Studio
1.  2026-11-02  Studio  Atlas Website
2.  2026-10-28  Studio  Marketing
3.  2026-10-25  Studio  Events
4.  2026-10-20  Studio  Archive 2025
Listing: 271aa0b04b894c3db8d4a01ff2db881f (15 min; optional --listing ID pins these rows)
Next: co asana tasks 1

$ co asana tasks 1 --assignee me --due-to 2026-11-09
2 open tasks in Atlas Website
1.  open  due 2026-11-07  Alex Chen  Launch checklist
2.  open  due 2026-11-09  Alex Chen  Renew domain
Listing: 4bfe020dd5fa4e1b8460806551f537b1 (15 min; optional --listing ID pins these rows)
Next: co asana task 1
```

Rows are aligned columns with the name last: projects show the modified day,
then team, `archived` and gid when present; tasks show status, due day,
assignee and, with `--ids`, the gid. An assignee or team longer than 16
terminal cells ends in `…`, so names stay on an 80-column line. Each row still
starts with its number (`1.`, `10.`), which is what `task 1` and `tasks 1`
take. The text layout is for people; scripts should read `--json`, whose
shape did not change.

In a colour terminal, `tasks` marks the due day red when an open task is past
due, yellow when it is due today, and dim when the task is done or has no due
day; your own name (the token's user) is bold and an unassigned `-` is dim.
The words carry the same meaning without colour (`NO_COLOR`).

`tasks` lists open tasks unless `--status done` or `all`, at most 20 (`-n` up
to 250), most recently modified first. A task with no due day is left out
whenever `--due-from` or `--due-to` is given. A task due at a time of day is
listed under that time's local day.

`co asana task <ref>` shows status, assignee, due day, followers, projects,
custom fields, link, description and comments. `co asana stories <ref>` shows
everything Asana recorded, oldest first, with who did it: comments and its own
activity such as assignments.

```text
$ co asana stories 1
3 stories on Launch checklist
  2026-11-02 09:00 Priya Nair  assigned: Priya Nair assigned to Alex Chen
  2026-11-02 09:01 Priya Nair  comment_added: Alex, can you own this? The site goes live on the 10th.
  2026-11-02 20:00 Alex Chen  comment_added: Yes, I'll finish it by 7 Nov.
Next: co asana task 1
```

`--json` prints Asana's own records on stdout and the `Next:` line on stderr.

## For co rem: `changes` and `show`

A REM source is its `co` command (design decision 081, #3249): REM asks
`co asana changes` what changed and `co asana show` for one task, and keeps no
copy of either. Both are read-only and you can run them yourself.

`co asana changes --since <time>` lists the tasks changed after that time,
oldest change first. The time needs its zone (`2026-11-01T09:00+11:00` or
`...Z`); without one it exits 2 before anything is sent. By default it reads
the tasks assigned to you, in every workspace of the account (one request per
workspace; `--workspace` reads one). `--project <row, ID or exact name>`,
repeatable, reads every task in those projects instead; with several
workspaces, a project name needs `--workspace` too. Completed tasks are
included, since completing one is a change, and so is a task with a new
comment. Deleted tasks are not listed, and neither is a task reassigned away
from you, unless `--project` names its project. A `--since` later than now
exits 2.

```text
$ co asana changes --since 2026-11-01T00:00+11:00
2 tasks assigned to you changed since 2026-11-01 00:00
  2026-11-02 20:30  1209000000000300  Launch checklist
  2026-11-03 20:55  1209000000000330  Book venue
Next: co asana show 1209000000000300
```

With `--json`:

```json
{
  "since": "2026-11-01T00:00:00+11:00",
  "until": "2026-11-21T07:15:56+00:00",
  "items": [
    {"id": "1209000000000300", "time": "2026-11-02T09:30:00.000Z", "title": "Launch checklist",
     "project": "Atlas Website", "link": "https://app.asana.com/0/1209000000000200/1209000000000300"}
  ]
}
```

`until` is when the read began: pass it as the next `--since` and nothing
changed in between is missed. A task changed while it was being read can
appear in both lists, so keep one per `id` and `time`. `time` is Asana's
`modified_at`; it is `null` when Asana sent none, and those come last.

`co asana show <ref>` prints what `co asana task` prints. With `--json` it is
one item in the shape REM reads from every source:

```json
{
  "id": "1209000000000300",
  "title": "Launch checklist",
  "text": "Final checks before the Atlas site goes live.\n\nComments (oldest first):\n- 2026-11-02T09:01:00.000Z Priya Nair: Alex, can you own this? ...\n- 2026-11-02T09:30:00.000Z Alex Chen (you): Yes, I'll finish it by 7 Nov.\n\n(1 activity record(s) by Asana, such as assignment or completion, not quoted)",
  "author": "Priya Nair", "author_id": "1209000000000101",
  "time": "2026-11-02T09:30:00.000Z",
  "link": "https://app.asana.com/0/1209000000000200/1209000000000300",
  "status": "open", "completed_at": null,
  "assignee": "Alex Chen", "assignee_id": "1209000000000100", "assigned_to_you": true,
  "due": "2026-11-07",
  "projects": ["Atlas Website"],
  "comments": [
    {"author": "Priya Nair", "author_id": "1209000000000101", "you": false,
     "time": "2026-11-02T09:01:00.000Z", "text": "Alex, can you own this? ..."},
    {"author": "Alex Chen", "author_id": "1209000000000100", "you": true,
     "time": "2026-11-02T09:30:00.000Z", "text": "Yes, I'll finish it by 7 Nov."}
  ]
}
```

`text` is the description, then every comment oldest first, `(you)` after the
token owner's own; Asana's own activity is counted, not quoted. `you` and
`assigned_to_you` compare Asana user IDs, never names, so a namesake is never
taken for you (`--json` reads who the token acts as for this). `author` is who
made the task. `completed_at` is when it was completed (`null` while open); a
comment after that moves `time` later, not `completed_at`. A citation
`asana:<id>` opens through `show`, so it shows the task as it is now; compare
`time` with when it was cited to tell whether it changed. A task deleted or no
longer visible exits 1.

## Write: preview, then `--yes`

```text
$ co asana update 1209000000001001 --due-on 2026-11-14
Preview — would change Launch checklist. Nothing changed in Asana.
  task:        Launch checklist  1209000000001001
  due:         2026-11-07 → 2026-11-14
Next: co asana update 1209000000001001 --due-on 2026-11-14 --yes

$ co asana update 1209000000001001 --due-on 2026-11-14 --yes
✓ Updated Launch checklist  1209000000001001: due 2026-11-14
Next: co asana task 1209000000001001

$ co asana comment 1209000000001003 "Thanks Bob, Wednesday works"
Preview — would comment on Send logo files. Nothing changed in Asana.
  task:        Send logo files  1209000000001003
  comment:     Thanks Bob, Wednesday works
Next: co asana comment 1209000000001003 'Thanks Bob, Wednesday works' --yes
```

- `update` changes only what you give: `--due-on YYYY-MM-DD`, `--done`, or
  `--open`. It refuses a task due at a time of day (exit 2), because
  `--due-on` would drop the time; change that one in Asana.
- `comment <gid> -` reads the text from standard input. The text is sent
  exactly as given, a trailing newline included.
- A write whose result is unknown (Asana timed out or answered 5xx after the
  request was sent) exits 1 with "the change may have been saved. Check before
  running it again." and a `Next:` that reads the task. It is never sent again
  automatically.

## Errors

Every failure prints `✗ <cause>` and one `Next:` command on stderr.

| exit | cause | printed (examples) | Next |
|---|---|---|---|
| 1 | no token | `ASANA_ACCESS_TOKEN is not set in ~/.co/keys.env. Create a personal access token at https://app.asana.com/0/my-apps, then save it` | `co env set ASANA_ACCESS_TOKEN <pat> --secret` |
| 1 | token rejected | `Asana rejected ASANA_ACCESS_TOKEN: Not Authorized. Make a new token at https://app.asana.com/0/my-apps` | `co env set ASANA_ACCESS_TOKEN <pat> --secret` |
| 1 | saved token will not open | `ASANA_ACCESS_TOKEN is saved encrypted but cannot be opened: no agent key at ~/.co/keys/agent.key. …` | `co init` (no agent key), otherwise save the token again |
| 1 | unknown or hidden task | `No Asana task 1209000000009999, or this token cannot see it (… HTTP 404)` | `co asana tasks "<project>"` |
| 1 | rate limit after retries | `Read 0 tasks, incomplete; nothing was listed: Asana asked to wait 30 s before the next request (HTTP 429). Try again later` | `co asana check` |
| 1 | list stopped part way | `Read 1 task, incomplete; nothing was listed: Asana: Server Error (HTTP 500)` | `co asana check`; listing again is safe |
| 1 | write result unknown | `Asana: Server Error (HTTP 500); the change may have been saved. Check before running it again.` | `co asana task <gid>` / `co asana stories <gid>` |
| 2 | stale or missing list | `No recent Asana projects list to take row 1 from` | `co asana projects` |
| 2 | row on a write without `--listing` | `Row 1 needs the --listing it came from before anything is changed; or give the task gid` | `co asana tasks "<project>"` |
| 2 | unknown project or workspace name | `No project named 'Website' in Atlas Studio` | `co asana projects` |
| 2 | bad date, `--done` with `--open` | `--due-on takes a date like 2026-10-16, not '14/11/2026'` | `co asana update --help` |
| 2 | task due at a time | `Task … is due at a time (…); --due-on would drop the time. Change it in Asana` | `co asana task <gid>` |

## Limits

- No create, delete, assign, rename, clearing a due date, or moving a task
  due at a time of day.
- `tasks` reads every page and filters locally; a very large project takes
  as many requests as it has pages of 100.
- `changes` without `--project` sees only tasks assigned to you now: a task
  reassigned to someone else drops out without a change being listed.
- `changes` uses `modified_at`. Asana documents that a new or deleted comment
  updates it; an edited comment may not, so such a task may not be listed.
- Personal access tokens only; no OAuth.

## Testing

```bash
pytest tests/unit/test_asana.py tests/unit/test_asana_commands.py   # fake Asana, no network
cd examples/co-asana-evals
co benchmark check co-asana
co eval run co-asana --agent agent.py --skill co-asana --invoke explicit --runs 1 --max-iterations 15
```

The eval drives the real commands against the synthetic workspace; it never
reaches Asana. See [examples/co-asana-evals/README.md](../../examples/co-asana-evals/README.md).
