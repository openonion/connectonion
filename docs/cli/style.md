# How `co` output looks

One visual standard for every `co` command (#1997). Commands produce it with
`connectonion/cli/style.py`, and `co audit co --style` checks it from outside,
using only what each command prints.

## The palette

These are the colours the CLI already used most. They were written down, not
invented:

| role | looks like | function |
|---|---|---|
| a command you can copy, including the one on a `Next:` line | cyan | `command("co rem status")`, `next_line("co rem status")` |
| a path | cyan, home written as `~` | `path(p)` |
| a heading or a result's first line | bold | `heading("Notebook")` |
| a number | bold number, unit in words | `count(2113, "message")` → `2,113 messages` |
| success | green `✓` | `ok("Gmail connected")` |
| warning (needs attention, did not fail) | yellow `!` | `warn("3 pages are stale")` |
| error | red `✗`, followed by a `Next:` | `error("Outlook token expired")` |
| detail (time, id, source) | dim | `dim("updated 3 min ago")` |

Each function returns a `str`, so `print()`, `typer.echo` and a log file all
accept it. Do not print Rich markup such as `[cyan]` through these functions.

## A status-style result

```
Notebook                                  ← heading(): one line that answers the question
  ✓ 412 pages, updated 3 min ago

Mail                                      ← section(title, rows): one line per item
  Gmail     ✓ connected, 2,113 messages
  Outlook   ✗ token expired
Next: co auth microsoft                   ← next_line(): one next step, on stderr
```

- The first line is the answer. Sections follow, with one line per item.
- Details (ids, timestamps, sources, raw counts) go behind `--verbose`.
- Never print an internal record as it is (`last_sync_at: 1759…`,
  `{'state': …}`). Put it in words, or give it a `--json` flag.

## Progress

- Known total: `with progress(total, "Reading mail") as bar: … bar.advance()`.
  In a terminal this is a bar with `n/total` and the elapsed time, and it is
  erased when the work finishes. Anywhere else it prints `Reading mail: 12/40`
  at each tenth of the total, so a log or a launchd run shows the command is
  still working.
- Unknown total: `with spinner("Asking Gmail"): …`. In a terminal this is a
  spinner with the elapsed time, erased when the work finishes. Anywhere else
  it prints nothing. Print the result after it.

## Plain when it should be plain

`styled(stream)` decides once for all of them, in this order:

1. `--json` → plain. The command calls `plain_output()`.
2. `NO_COLOR` set → plain.
3. `FORCE_COLOR` set → colour, even into a pipe.
4. `TERM=dumb` → plain.
5. Otherwise colour only when the stream is a terminal. A pipe, a log file and
   launchd get plain text.

Either way the words are the same. Styling changes how a word looks, never
which words are printed.

## What `co audit co --style` checks

It runs each help page twice in an empty HOME and working directory: once
under a 200-column pseudo-terminal, and once into a pipe with `NO_COLOR=1`. A
leaf command whose name is `status`, `check`, `ls` or `doctor` and whose help
page says `Read-only` is also run the same two ways. Nothing else is run.
Every run is killed after 20 seconds.

| rule | fails when |
|---|---|
| `hangs` | a run did not finish in 20 s |
| `styled` | the terminal run has no colour or weight at all |
| `command_colour` | the command after `Next:`, `Example:` or `Back:` is not styled in the terminal |
| `plain` | the `NO_COLOR` pipe run contains an escape code |
| `same_words` | with escape codes removed and only what stays on screen kept (spinner frames erased), the words differ from the pipe run |
| `field_dump` | a run (not a help page) prints more than two `snake_case:` or `camelCase =` fields, or Python/JSON literals |

```bash
co audit co --style              # every page, scored per rule and by group
co audit co gmail --style        # one group
co audit co --since base.json --style   # only pages changed since an inventory
```

The `help-gate` workflow runs the last form on every PR that touches the CLI.
For now it reports without blocking. It will block once the `Example:` and
`Back:` lines Typer renders are coloured in one place. Today they are
unstyled on every page, so every PR would fail on lines it did not write.
