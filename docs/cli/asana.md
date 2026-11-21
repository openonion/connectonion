# Asana tasks: `co asana`

Read your Asana projects, tasks and their discussion from the terminal, move a
due date, mark a task done or open, and comment, as yourself. Built on Asana's
REST API (`https://app.asana.com/api/1.0`) with a personal access token.
The agent-facing guide is the `co-asana` Skill
(`connectonion/useful_skills/co-asana/SKILL.md`).

`check`, `projects`, `tasks`, `task` and `stories` are read-only. `update` and
`comment` print a preview and change nothing until you add `--yes`.

> Status: the examples below were produced on 2026-11-02 by the real commands
> against the synthetic workspace in `examples/co-asana-evals` (no network).
> The reads, `update` and `comment` were also run against a real workspace
> while they were built (October 2026).
> The `projects` and `tasks` rows are shown in the column layout those
> commands print since 2026-11-12; the data is the same.

## Setup

Run, in a terminal:

```bash
co auth asana
```

It makes the token in the co browser, in a tab of its own (`co-auth-asana`;
the shared main tab is left alone). If the co browser has no Asana cookies, it
asks once to copy your Chrome cookies for asana.com into it (nothing else is
copied), or waits while you sign in in its window. It opens Asana's developer
console and the new-token form, names the token `co on <this computer> <date>`
and marks what is left to you; you accept Asana's API terms and press
**Create token**, and it reads the token back, checks it with
Asana and saves it encrypted, as `co env set ASANA_ACCESS_TOKEN <pat> --secret`
does (that works too). A token that already works is kept, and no new one is
made. The token is never printed.

However it ends, and before any paste is asked for, the console tab is
replaced by one line, so the token is not left on screen, and the Asana cookies
it copied or you signed in with are cleared from the co browser again. Asana
cookies the co browser already had are left alone.

If the co browser is not available, cannot say which cookies it holds, holds
Asana cookies but no sign-in (a sign-in typed there could not be told apart and
cleared), or does not get as far as a token (no sign-in, no Create within five
minutes), it falls back to pasting: it opens <https://app.asana.com/0/my-apps> in your default
browser and asks for the token, hidden. `co auth asana --paste` goes straight
there and never uses the co browser. Without a terminal it reads one line from
standard input (`co auth asana --paste < token.txt`) and stops after 30 seconds
if nothing arrives.

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
| 1 | no token | `ASANA_ACCESS_TOKEN is not set in ~/.co/keys.env. Create a personal access token at https://app.asana.com/0/my-apps; co auth asana saves it (or co env set ASANA_ACCESS_TOKEN <pat> --secret)` | `co auth asana` |
| 1 | token rejected | `Asana rejected ASANA_ACCESS_TOKEN: Not Authorized. Make a new token at https://app.asana.com/0/my-apps and save it with co auth asana` | `co auth asana` |
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
