# `co audit` — is every command's help something an agent can act on?

For an agent, a `co` help page is the prompt that describes the tool. `co audit`
checks every page against the contract in #1643: hard rules first, a model's
judgement last.

```bash
co audit                              # every command, hard rules only (about 20 s)
co audit gmail send                   # one command or group
co audit gmail send --review          # then a model judges the page
co audit --inventory > base.json      # fingerprint every page
co audit --since base.json --review   # only pages added or changed since then
co audit --json                       # findings for scripts
```

Exit 0 means no problem was found; exit 1 lists each problem with its fix.

## Hard rules (free, deterministic, offline)

Each page is read under an empty HOME and working directory.

| rule | fails when |
|---|---|
| `exit0` | `--help` does not exit 0 |
| `writes` | reading help created a file |
| `usage` | no `Usage:` line (hand-written pages such as `co proxy` are exempt) |
| `example` | no `Example:` line |
| `self_example` | no example runs this command itself |
| `flags` | an example uses a flag the command does not have (skipped for commands that parse their own arguments) |
| `refs` | an Example, Next or Back line names a `co` command that does not exist |
| `side_effect` | the page never says what it changes: Read-only, Writes, Sends, Deletes, Removes, Creates, Changes, Charges, Deploys, Installs, Uploads, Publishes, Starts, Stops or Runs |
| `back` | no `Back:` line (generated for every page, so this means the page was hand-written) |
| `private` | an example contains a real home path or a full 0x address |
| `lists_children` | a group page does not list every subcommand. Because `co --help` is a group page, this rule is what makes every command reachable by following printed names from the top |

CI runs the same rules on every PR, through `tests/unit/test_cli_help_contract.py`,
and a failure blocks the merge. The command and the test share one engine
(`connectonion/cli/audit.py`), so they cannot disagree.

## Model review (`--review`)

Only pages that pass every hard rule are reviewed. A text-only model reads
the page and judges four things:

- **clear**: a newcomer knows when to use the command from the first line;
- **effects match**: what the page says it changes fits the command;
- **example realistic**: a user would actually run it;
- **simple**: plain words, no internal jargon.

It returns one concrete rewrite for the weakest sentence. A model's verdict
varies between runs, so in CI this is advisory: the `help-gate` workflow
reviews only the pages a PR added or changed and writes the result to the job
summary without blocking. Pin `--model` when comparing two runs.

`co wiki` keeps its own reviewed pages and contract test, and is not audited
here.
