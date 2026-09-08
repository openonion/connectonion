# `co env` — see, set and repair the selected env file

Added in 1.8.4. `co env` works on whichever env file this invocation selected:
global `~/.co/keys.env` by default, or the file named by `co --env-file PATH`
(see [Environment selection](environment.md)). It never selects a file itself,
and it never touches your shell's variables.

```bash
co env                              # every setting, secrets masked, with its source
co env show --reveal                # the same with full values (keep out of shared logs)
co env path                         # the selected file's path, bare, for $(co env path)
co env get OPENAI_API_KEY           # one value, bare, as a command would see it
co env set OPENAI_API_KEY sk-...    # save one setting; creates the file if needed
co env unset OPENAI_API_KEY         # remove one setting
co --env-file ./project.env env     # the same commands on a project file
```

## What `co env` shows

```
Env file: ~/.co/keys.env (global)
SETTING             VALUE               SOURCE
OPENONION_API_KEY   eyJhbG…********     file
MODEL               co/gemini-3.7-flash process overrides file
GOOGLE_EMAIL        me@example.test     file, ignored: the process supplies the Google record
Secrets are masked; add --reveal to see them. Keep --reveal out of shared logs.
Next: co env set <KEY> <value>
```

- **SOURCE** says whether a setting wins. `process overrides file` means your
  shell exports the same name with a different value, and process values win.
  `ignored` marks a provider record the file holds while the shell supplies
  another one; records are used whole, never merged (see #1444).
- Values are masked when the name says secret: `KEY`, `TOKEN`, `SECRET`,
  `PASSWORD`, `PHRASE`, `CREDENTIAL`, `PRIVATE`. An email or a model name shows
  in full.
- The file is read as-is; nothing is loaded into the process.

## `set` and `unset` rules

`co env set` rewrites the file atomically under the same lock that provider
refresh uses, keeps every comment and unrelated line, quotes values with
spaces, and leaves the file owner-only (`0600`) on Unix. Existing keys are
replaced in place; new ones are appended.

Three names are refused, each with the command to use instead:

| Name | Why | Use instead |
| --- | --- | --- |
| `AGENT_CONFIG_PATH` | It chooses which global directory is read, so a file inside that directory cannot set it | `export AGENT_CONFIG_PATH=/path/to/.co` in your shell |
| `GOOGLE_ACCESS_TOKEN`, `GOOGLE_REFRESH_TOKEN`, `GOOGLE_TOKEN_EXPIRES_AT`, `GOOGLE_SCOPES`, `GOOGLE_EMAIL` | An account record is written as a whole; one edited field could describe a different account than the rest | `co auth google` |
| The same five `MICROSOFT_*` fields | Same rule | `co auth microsoft` |

`co env unset` on any one of those record fields removes the **whole** record,
and says so. That is the supported way to disconnect an account from a file.

If your shell exports the name you just set, `set` still saves it and then
tells you the shell's value will keep winning until you `unset` it there.

## A broken file

One malformed line in `~/.co/keys.env` — a pasted key with a stray quote, a
line without `=` — stops every `co` command with exit 2:

```
~/.co/keys.env: invalid syntax on line 7. Next: co env
```

`co env` is the one command that still runs on that file. It repeats the line
number (never the line's contents, which may be a secret) and exits 2 until
the line is fixed in an editor. `co env set` refuses to rewrite a file it
cannot parse, so the broken line is never silently dropped.

## Exit codes

| Exit | Meaning | Next command (printed) |
| --- | --- | --- |
| 0 | Done | `co env set <KEY> <value>`, `co env get <KEY>`, or `co init` when the global file does not exist yet |
| 1 | `get` or `unset` named a setting that is not there | `co env set <KEY> <value>` / `co env` |
| 2 | Bad name, protected name, missing explicitly selected file, or a file that does not parse | The command named in the message: `co env`, `co env set …`, `co auth google`, or a shell `export` |

`co env path` and `co env get` print only the value so they compose with
`$(...)`; they are the two commands that print no `Next:` line.

## Where else the selected file shows up

`co status`, `co doctor` and `co keys` inspect the same selected sources and
name `co env set …` as the fix for a missing provider key. `co gmail`,
`co gdrive`, `co gcalendar`, `co youtube`, `co outlook` and their SDK clients
say which file (or that the process) supplied an incomplete account record,
and point at `co env` before asking you to re-authorize.
