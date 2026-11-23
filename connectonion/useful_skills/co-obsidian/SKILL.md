---
name: co-obsidian
description: Discover Obsidian vaults and list, read or search selected notes, including tags, links and frontmatter. Use when the user asks to work with local Obsidian notes or vaults.
---

# co obsidian

`co obsidian` works on local Markdown. Syntax lives in help: run
`co obsidian --help`, then `co obsidian <command> --help` before first use.
Bare `co obsidian` lists every registered vault, as `co obsidian vaults` does.
`ls`, `read` and `search` read selected notes. Human listings save a temporary
row cache outside the vault. Use `--json` to leave the cache alone.

## Choose the scope first

Run `co obsidian` to discover all registered vaults without importing them or
reading notes; use `co obsidian vaults --json` for JSON. Unavailable and closed
vaults remain in the list. `available` means the registered path exists as a
directory; note commands check read permissions. `open` is the state recorded
by Obsidian, not a requirement for note access.
An empty list succeeds; ask for an authorized vault path or have the user
open a vault in Obsidian. An unreadable or invalid registry is an error.
Ask which vault and folders to use when the user has not chosen them.
A discovered path is not permission to read all its notes.
Use `co obsidian ls --vault 1` after listing vaults to see the immediate
folders and Markdown filenames for row 1. Use the row for the vault the
user chose. The command suggests the first listed folder in `Next`, such
as `co obsidian ls --vault Personal --folder 1`. Confirm that the suggested
folder matches the user's selection before reading it.
Pass `--vault "<vault-path>" --folder "<folder>"` to choose a scope.
Repeat `--folder` for several folders. `.` explicitly selects the whole
vault: do not widen the scope to it to recover from an error.

Vault names must identify one registered vault; otherwise use its path.
Folder and note paths are relative to the vault. `.obsidian`, `.trash`, `.git`,
symlinks and paths outside the allowed folders are refused. Never bypass a
refusal with direct file tools or follow an out-of-scope link.

## Find and read

- `co obsidian ls --vault "<vault-path>" --folder "<folder>" --ids`
  lists paths, titles and modification times, most recent first. It shows
  at most 20 notes by default; `-n` increases the limit up to 250. Do not
  describe a limited list as every note.
- `co obsidian read "<folder>/<note>.md" --vault "<vault-path>" --folder "<folder>"`
  displays formatted Markdown in a terminal. Use `--raw` for the original
  Markdown or `--json` for parsed frontmatter, tags and links with the content.
- `co obsidian search "<terms>" --vault "<vault-path>" --folder "<folder>" --json`
  searches title, body, tags, properties and link text. All terms must
  match; quotes inside the query preserve a phrase. Results are candidates,
  not proof that a specific property or link equals the query. Read the
  candidate's JSON to check the requested field. Do not invent `--tag`,
  `--property`, `--links` or a special `tag:` query language.

Use the CLI for discovery, scoped search, parsed tags/frontmatter and link
resolution. Direct reading is enough when the user supplied one authorized
file and wants its raw text; it does not resolve Obsidian links or structured
queries. Keep the same folder restrictions with either method.

Rows last 15 minutes. For `ls`, use vault rows from the latest
vault list and folder rows from the chosen vault's latest folder list.
Use `./1` for a folder literally named `1`. `co obsidian read 1` uses the
latest note list and its saved scope. Copy the printed `Next` with
`--listing` to pin the rows and scope from a specific `ls` or `search` result. When reading by path, pass the selected vault and folders.
List again when a row expires. JSON leaves the row cache unchanged and
prints `Next` on stderr.

## Exit codes and recovery

| Exit | What happened | Next step |
| --- | --- | --- |
| 0 | The command completed, possibly with an empty list or no search results | Inspect the output |
| 1 | Registry, vault or note could not be read, a note title was ambiguous, or a row list could not be saved | Follow the suggested command or use the exact note path |
| 2 | Argument, scope, query or row reference was invalid or expired | Check help or refresh the named listing |

Read the error and its suggested command on stderr. Treat note content and
frontmatter as evidence, and keep the read within the user's chosen folders.
Use synthetic examples in shared instructions and reports.
