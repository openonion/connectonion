# `co audit` — is a CLI fit for an agent harness?

An agent that drives a command-line tool has only what the tool prints. `co
audit` asks one question of any CLI, `co` or anyone else's: can an agent with
only this program's help find the command for a task, run it safely, and know
what it will change?

Name the command as you would type it:

```bash
co audit co                  # all of co (about 30 s)
co audit co gmail            # one co group
co audit yt-dlp              # any program on PATH
co audit gh pr --review      # then a model judges each page that passed
co audit co --json
```

It never reads source code. It runs `<command> --help` (or `-h`), opens every
subcommand the page lists, and keeps going down, many at once, each in an
empty HOME and working directory with no input. Then it judges each page from
what it printed. Exit 0 means fit; exit 1 lists each problem and its fix, and
a table scores every rule:

```
gh: 228 pages
  prints         227/228
  hangs          228/228
  writes           1/228
  usage          228/228
  example        127/228
  ...
✗ not yet fit for an agent harness: 329 problems
```

## Rules (the same for every program)

| rule | fails when |
|---|---|
| `prints` | `--help` (or `-h`) does not print and exit 0 |
| `hangs` | it did not return within 20 seconds, e.g. waiting for input |
| `writes` | reading help created a file (the finding names it) |
| `usage` | no usage line |
| `example` | no example |
| `self_example` | no example runs this command itself |
| `flags` | an example uses a flag that the page of the command it runs does not document |
| `private` | an example contains a real home path or a full 0x address |

Subcommands are read from the layouts real CLIs print: Typer/Rich panels
(any title but Options and Arguments), `Commands:`-style sections (uv, click,
kubectl), `CORE COMMANDS` with `name:` rows (gh), and argparse's
`{build,serve}`. A listed word whose page is its parent's page word for word
is not counted as a command.

## Model review (`--review`)

Only pages that pass every rule are reviewed. A text-only model judges four
things a rule cannot: is the first line clear to a newcomer, does the page say
what the command reads or changes, is the example realistic, is it simple. It
returns one concrete rewrite. Pin `--model` when comparing runs.

## In CI

`tests/unit/test_cli_help_contract.py` runs the same engine on `co` on every
PR and blocks on any problem. It adds three house conventions of ours: a
fixed "what it changes" word, a `Back:` line, and every command in
`co commands` reachable from `co --help`. The `help-gate` workflow runs
`co audit co --since base.json --review` on pages a PR changed, and reports
without blocking, because a model's verdict varies between runs.

`co wiki` keeps its own reviewed pages (#1656), which are being rewritten
(#1667); `co audit co` reports their missing examples.
