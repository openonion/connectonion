# `co audit` — is a CLI fit for an agent harness?

An agent that drives a command-line tool has only what the tool prints. `co
audit` asks one question of any CLI, `co` or anyone else's: can an agent with
only this program's help find the command for a task, run it safely, and know
what it will change?

Name the command as you would type it:

```bash
co audit co                  # all of co (about a minute)
co audit co gmail            # one co group
co audit co onenote          # OneNote help, including numbered pages and read
co audit yt-dlp              # any program on PATH
co audit gh pr --review      # then a model judges each page that passed
co audit co --json
```

It never reads source code. It runs `<command> --help` (or `-h`), opens every
subcommand the page lists, and keeps going down, many at once, each in an
empty HOME and working directory with no input. Then it judges each page from
what it printed. Exit 0 means fit; exit 1 lists each problem and its fix, and
a table scores every rule:

For a Python CLI installed with `pip --user`, it preserves the original Python
user-package path while isolating HOME. Otherwise the entrypoint could fail to
import its package before printing help, and the audit would mistake that for
an unreachable command.

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
| `params` | an option or argument has no description |
| `look` | run again as a person's terminal runs it, the page says different words, or it is coloured in a pipe; for `co`, also a page with no colour in the terminal |

`look` runs each checked page a second time with `FORCE_COLOR=1`,
`TERM=xterm-256color` and 100 columns (the first run is `NO_COLOR=1`,
`TERM=dumb`, 200 columns), so an audit takes about twice as long. Words are
compared without colour, whitespace and frame characters, and in any order,
because a table narrowed to 100 columns folds a long value beside its
description; a value cut to `connec…` is a different word. A plain page in a
terminal fails only for `co`: many good CLIs print plain help on purpose, and
nothing about that stops an agent.

## Look (the standard `co` holds itself to, #1997)

Every `co` command prints through `connectonion/cli/style.py`:

- **Palette**: commands (examples, Next lines) bold cyan, counts bold, paths
  dim, warnings yellow, errors bold red, section titles bold underlined.
  A page written as one string goes through `style.markup()`.
- **Next line**: a result ends with `Next: <command>`, drawn by
  `style.next_line`.
- **Status layout**: a header line, then sections, one line per item; details
  behind `--verbose`.
- **Progress**: `style.progress()`, a bar with i/N when the total is known, a
  spinner with elapsed time otherwise; nothing is drawn off a terminal.
- **Plain when it should be plain**: no escape codes under `NO_COLOR`, in a
  pipe, a log or launchd, or with `--json`; the same words either way.

Beside the help pages, `co audit co` runs the read-only status commands in
`audit.STATUS` (`co status`, `co doctor`, `co commands`) both ways, and fails
a `Next:` line there that is not drawn the way `style.next_line` draws it.

Subcommands are read from the layouts real CLIs print: Typer/Rich panels
(any title but Options and Arguments), `Commands:`-style sections (uv, click,
kubectl), `CORE COMMANDS` with `name:` rows (gh), and argparse's
`{build,serve}`. A listed word whose page is its parent's page word for word
is not counted as a command.

## Model review (`--review`)

Only pages that pass every rule are reviewed. A text-only model judges five
things a rule cannot: is the first line clear to a newcomer, does the page say
what the command reads or changes, is the example realistic, is it simple,
and, when it acts on a listed item, can the user refer to that item briefly
instead of copying a long provider ID or full title? Commands that do not
select listed items pass the last question. It returns one concrete rewrite.
Pin `--model` when comparing runs.

## In CI

`tests/unit/test_cli_help_contract.py` runs the same engine on `co` on every
PR and blocks on any problem, `look` included. It adds three house conventions of ours: a
fixed "what it changes" word, a `Back:` line, and every command in
`co commands` reachable from `co --help`. The `help-gate` workflow runs
`co audit co --since base.json --review` on pages a PR changed, and reports
without blocking, because a model's verdict varies between runs.

`co rem` keeps its own reviewed pages (#1656), which are being rewritten
(#1667); `co audit co` reports their missing examples. They are held to
`look` like every page, except the ones in the test's `LOOK_PENDING`, a set
that can only shrink and empties when their rewrite (#1996) lands.

OneNote also has a behavioral terminal journey in `tests/unit/test_onenote.py`:
`co onenote ls` → `co onenote pages 2` → `co onenote read 1`. The test checks
that both numbers resolve to the IDs that were displayed, even when two pages
share a title. The help review can flag a missing short reference, but it
cannot verify that a displayed number resolves to the right item.
