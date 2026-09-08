---
name: co-env
description: See, set, remove and repair settings in the env file a `co` invocation selected — global ~/.co/keys.env by default, or the file named by `co --env-file PATH` — with `co env`. Use when a command says a key is missing, "Next: co env", "account not connected in <file>", or when the user asks which env file is in use or wants an API key saved.
---

# co env

**Always read the output, not just the exit code.** `co env path` and
`co env get` print a bare value and no tip, so they compose with `$(...)`;
every other `co env` command ends with one `Next:` line.

## Which command

| You want to | Run |
| --- | --- |
| See which file is in use and what it holds (secrets masked) | `co env` |
| See full values (never paste into shared logs) | `co env show --reveal` |
| The file's path, for a script | `co env path` |
| One value as a command would see it (process wins, then file) | `co env get KEY` |
| Save a setting, creating the file if needed | `co env set KEY VALUE` |
| Remove a setting | `co env unset KEY` |
| Connect a Google / Microsoft account | `co auth google` / `co auth microsoft` — not `co env set` |
| Disconnect one from this file | `co env unset GOOGLE_EMAIL` (removes the whole record) |
| Do any of this on a project file | `co --env-file /abs/path/.env env …` (selector **before** `env`) |

## The 80% commands

```bash
co env                                   # file, settings, sources, next step
co env set OPENAI_API_KEY "$KEY"         # quote values; spaces are fine
co env get MODEL                         # bare value
co --env-file ./project.env env set MODEL co/gemini-3.7-flash
```

## Gotchas that change a result

- **SOURCE column.** `process overrides file` means the shell exports the same
  name; the file's value is not what commands see. `set` still saves it and
  prints the `unset KEY` you need in the shell.
- **Provider records are all-or-nothing.** `set` refuses the five `GOOGLE_*`
  and five `MICROSOFT_*` account fields (exit 2, names the auth command).
  `unset` on any one of them removes all of them and says so.
- **`AGENT_CONFIG_PATH` cannot be set here.** It chooses which directory is
  read; `set` refuses it and prints the shell `export` to use.
- **A broken file stops everything else.** Any other command exits 2 with
  `<file>: invalid syntax on line N. Next: co env`. `co env` still runs, repeats
  the line number, never the line, and refuses `set` until the line is fixed
  in an editor.
- **Nothing here selects a file.** `co env` shows the file the invocation
  already chose. To switch, put `--env-file` before the command.

## Exit codes

| exit | provoked by | next command (printed) |
| --- | --- | --- |
| 0 | done; or the global file does not exist yet | `co env set <KEY> <value>` · `co env get KEY` · `co init` |
| 1 | `get`/`unset` of a setting that is not there | `co env set KEY <value>` · `co env` |
| 2 | bad name · `AGENT_CONFIG_PATH` · provider record field · missing `--env-file` target · file does not parse | `co env set <KEY> <value>` · shell `export …` · `co auth google|microsoft` · `co --env-file … env set …` · `co env` |
