# Linear issues: `co linear`

List, read, search, create, update and comment on Linear issues from the
terminal, as yourself. Built on Linear's GraphQL API
(`https://api.linear.app/graphql`) with a personal API key (#2049).

Every read is read-only. `create`, `update` and `comment` print a preview and
change nothing until you add `--yes`.

> Status: run against a real workspace on 2026-10-01 (every read, an unknown
> issue and state, and create → comment → update through the real_api test),
> and against a fake Linear in the unit tests; see [Testing](#testing).

## Setup

1. In Linear, open **Settings → Security & access → Personal API keys** and
   create a key. It starts with `lin_api_`.
2. Save it, encrypted:

   ```bash
   co env set LINEAR_API_KEY lin_api_... --secret
   ```

   Without `--secret` it is written in plain text to `~/.co/keys.env`, which
   also works. A `LINEAR_API_KEY` exported in your shell wins over both.
3. Check it:

   ```bash
   co linear check
   # ✓ Linear workspace Acme linear.app/acme
   #   Acting as Aaron <aaron@example.com>
   # Next: co linear issues --mine
   ```

The key acts with your permissions. Issues and comments it creates are
yours.

## Names, not ids

Issues are named by the identifier people use, `ENG-123`. Everything else
is named the way Linear shows it, and the command looks up the id:

| you give | it means | list them with |
|---|---|---|
| `--team ENG` | a team key (or exact team name) | `co linear teams` |
| `--state "In Progress"` | a workflow state; on `update`, in the issue's own team | `co linear states --team ENG` |
| `--project "Q4 Launch"` | a project name | `co linear projects` |
| `--label bug` | a label of that team or of the workspace | `co linear labels --team ENG` |
| `--assignee me` / `--assignee bo@example.com` | you, or a member's email | `co linear users` |
| `--priority 2` / `--priority high` | 0 none, 1 urgent, 2 high, 3 medium, 4 low | |

Names are matched without regard to case. An unknown name exits 1, lists the
valid ones and names the command that lists them:

```text
✗ No label in ENG 'bgu'. Valid: Bug, auth
Next: co linear labels --team ENG
```

## Commands

### Read

```bash
co linear issues --mine                         # your open issues, newest update first
co linear issues --team ENG --state "In Progress" -n 50
co linear issues --project "Q4 Launch" --json
co linear issue ENG-123                         # details, labels, link, description, comments
co linear search "login redirect"               # Linear's full-text search, open or closed
co linear teams | projects | states | labels | users
co linear check
```

`issues` leaves out completed and canceled issues unless `--state` names one
(`--state Done` lists finished work). Lists print one line per issue:

```text
2 open issues assigned to you
ENG-2  In Progress  High         Aaron  2026-09-30  Login redirect loops
ENG-1  Todo         No priority  -      2026-09-01  Old crash
Next: co linear issue ENG-2
```

`--json` prints the same fields (`id`, `title`, `state`, `assignee`,
`priority`, `updated`) as a JSON array on stdout; the `Next:` line goes to
stderr so stdout parses. `co linear issue ENG-123 --json` adds `url`, `team`,
`project`, `labels`, `created`, `description` and `comments`.

### Write: preview, then `--yes`

```bash
co linear create "Login redirect loops" --team ENG --label bug --priority 2 --assignee me
co linear update ENG-123 --state Done --assignee me --priority 1
co linear comment ENG-123 "Fixed in #42"
```

Each prints what it would do, with the names already resolved, and the exact
command to run with `--yes`:

```text
Preview — would change ENG-2 Login redirect loops. Nothing changed in Linear.
  state:       In Progress → Done
Next: co linear update ENG-2 --state Done --yes
```

A long description or comment can come from standard input with `-`:

```bash
cat report.md | co linear create "Crash on login" --team ENG --description - --yes
echo "Fixed in #42" | co linear comment ENG-123 - --yes
```

`create` puts the issue in the team's default state. `update` changes only
the fields you give. Linear notifies the issue's subscribers of updates and
comments.

## Errors

Every failure exits 1 and prints the cause and one `Next:` command on stderr.

| cause | printed | next |
|---|---|---|
| no key | `LINEAR_API_KEY is not set in ~/.co/keys.env. Create a personal API key in Linear Settings → Security & access → Personal API keys, then save it` | `co env set LINEAR_API_KEY lin_api_... --secret` |
| key revoked or wrong | `Linear rejected LINEAR_API_KEY: You need to authenticate to access this operation. …` | `co env set LINEAR_API_KEY lin_api_... --secret` |
| unknown issue | `No issue ENG-999 in this workspace` | `co linear search "<words from its title>"` |
| unknown name | `No team 'XYZ'. Valid: ENG, OPS` | the listing command |
| any other GraphQL error | `Linear: <Linear's message>` | `co linear check` |

`update` with nothing to change exits 2 and names `co linear update --help`.

## Limits

- Listings read one page of up to 250 records (teams, states, labels,
  projects, members). A workspace larger than that is not paged yet.
- Assignees are `me` or an email; a display name is not matched.
- No delete, archive, label editing, cycles or OAuth in this version.

## Testing

```bash
pytest tests/unit/test_linear_commands.py                 # fake Linear, no network
pytest -m real_api tests/e2e/real_api/test_real_co_linear.py -s
```

The real test finds the key the way the commands do (shell, `~/.co/keys.env`,
then the `--secret` store), and skips when it is set nowhere.

The real test reads every listing, then creates one issue titled
`[co linear real_api test] safe to close …` in the first team (or
`LINEAR_TEST_TEAM`), comments on it, and moves it to a completed state. The
closed issue stays in the workspace.
