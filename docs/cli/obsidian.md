# Obsidian notes from the terminal

`co obsidian` discovers local vaults and lists, reads and searches Markdown
notes in selected folders. `create` and `append` add explicit, preview-bound
writes. The commands run offline without a model.
Run it without a subcommand to list every vault registered in Obsidian,
including unavailable ones. `co obsidian --help` shows the command overview
without reading the registry or any notes.

Run `co copy co-obsidian` from an agent project to install the optional
usage skill, which explains command choice and recovery. Run
`co obsidian <command> --help` for options and examples.

## Choose what may be read

All examples use placeholders and synthetic text. Substitute a vault you
have authorized and a folder relative to it. Discovery grants no permission
to read the whole vault. Names must be unique; paths remove name ambiguity.

```sh
co obsidian
co obsidian vaults
co obsidian vaults --json
co obsidian ls --vault 1
co obsidian ls --vault Personal --folder 1
co obsidian read 1
co obsidian ls --vault "<vault-path>" --folder "<folder>" --ids
co obsidian read "<folder>/<note>.md" --vault "<vault-path>" --folder "<folder>"
co obsidian search "<terms>" --vault "<vault-path>" --folder "<folder>" --json
```

Both `co obsidian` and `co obsidian vaults` list all registered vaults with
their names, paths, availability and open status. They read the vault registry
without opening or changing notes. Numbered output saves vault references
outside the vault for 15 minutes; `co obsidian vaults --json` does not save them.
`Next` suggests a command for the first available vault, using its row number
when one was saved, otherwise its path. A unique vault name or path also works
for `--vault`.
`available` means the registered path exists as a directory; note commands
check read permissions. `open` / `not open` is Obsidian's recorded app state;
a closed vault can still be read by the CLI.
An empty list succeeds. Open a vault in Obsidian to register it, or use an
authorized path directly with `--vault`. Registry failures report an error
and a recovery command rather than pretending the list is empty.

With no `--folder`, `ls` shows immediate folders and Markdown filenames at
the vault root without opening notes. `Next` suggests a command for the first listed folder.
Dot-prefixed folders appear after other folders. For an empty selected
folder, `Next` returns to the vault's folder list.
`ls` uses the latest vault list and the latest folder list for the chosen
vault. Rows last 15 minutes. List again when a row expires. Use `./1`
for a folder literally named `1`. The first 500 entries in a vault or folder
list have row shortcuts. Every entry can be selected by path.

Repeat `--folder` to select several folders. `.` deliberately selects the
whole vault. `.obsidian`, `.trash`, `.git`, symlinks and escaping paths remain
excluded. Do not widen a user's selection to work around a failure.
Scoped note commands index and resolve links only within the selected folders.
When a link has no target in those folders, `read --json` leaves its
`resolved_path` as `null`.

Navigation, note reads and cached rows keep the same validated vault and folder
paths. If an ancestor is redirected after selection, the command refuses the
changed location instead of reading another vault's notes. List again after
intentionally moving a vault.

With a folder selected, `ls` shows the 20 most recently modified notes by
default. Use `-n` to show up to 250 notes.
Numbered rows show filenames and add a distinguishing parent path for repeated
names. Use `--ids` to see the full vault-relative paths.
`search` matches every term across title, body, tags, properties and links;
quoted phrases inside the query stay together. It has no `--tag` or
`--property` flag. Search for candidates, then use `read --json` to inspect
frontmatter, tags and resolved links before asserting a field match.
In the terminal, each result groups its title, relative path, modification
time in UTC, matched fields and excerpt.

In a terminal, `read` shows the title and vault-relative path, then the
properties and formatted Markdown. Use `--raw` to see the original Markdown.
Piped or redirected stdout receives the original Markdown by default.
`--json` returns the full note record. `Next` shows a search command on its
own line on stderr, using the same folders and a unique registered vault name
when possible. Direct file reading is sufficient for an already authorized
file's raw text. Use CLI metadata parsing for structured Obsidian questions.
Neither method permits scope expansion.

Note lists save their row numbers for 15 minutes outside the vault.
`co obsidian read 1` uses the most recent note list and its saved scope.
Get note numbers from `ls --folder` or `search`.
Copy the suggested read command or pass `--listing <id>` to use a specific
list. If you give `--vault` with a note number, include `--folder` too.
Explicit scope flags must match the original vault and folders.
Vault and folder rows apply to `ls`. For scripts, use explicit paths.
JSON leaves the row cache unchanged and prints `Next` on stderr.
Without a folder, `ls --json` returns `vault`, `folders` and `notes` filenames.
The help examples use `Personal` as a vault name and `Course` as a folder name.
Replace those names with your selected scope. Examples without
`--vault` assume one available vault or a saved list of notes. If a folder-based
example finds several vaults, add `--vault` with the name or path you chose.

## Changed notes and live source reads

Two additional read-only commands expose the same top-level fields as the
Asana source CLI. They work offline and write no files: no saved bodies,
snapshots, cursor, listing cache or source registry.

```sh
co obsidian changes --since 2026-11-20T00:00:00Z --vault Personal --folder Course --json
co obsidian show "<id-from-changes>" --vault Personal --folder Course --json
co obsidian show Course/Note.md --vault Personal --folder Course --json
```

Use the authorized vault and folder **paths** on both calls; repeat `--folder`
for multiple folders in that vault. A folder is required even if only one
vault is available. `.` is a deliberate whole-vault selection, never a
fallback for an error. These commands do not use temporary row numbers.

For a shorter manual reference, `show` also accepts the vault-relative `path`
printed by `changes`, such as `Course/Note.md`. Quote paths containing spaces.
Prefix a path with `./` if it starts with a dash or resembles an ID or citation.
The printed next command uses `./` plus this path for human output and the stable ID
for JSON output. Both forms read one file through the same folder checks and
return the same stable `id`; no row cache is needed. Saved citations continue
to use that ID with its vault binding, not a path or a row number.

`changes` returns `{"since": "…", "until": "…", "items": […]}`. Each item has
`id`, `title`, `time`, `path`, `folder` and `link`. It examines filenames and
modification times only; it does not open any Markdown body. Items are sorted
oldest first, with relative path as the tie-breaker. Overlapping folders do
not duplicate items. A failed scan returns an error, never partial JSON.

`--since` must include a timezone and cannot be in the future. `until` is
captured before the source is scanned. Both bounds are inclusive, so a caller
can safely repeat a boundary item. After successfully processing the whole
result, the caller may retain `until` for the next read and deduplicate by
`id` and `time`. These commands do not save that cursor themselves. Files
edited after `until` wait for a later call. Files with future timestamps wait
until the clock catches up. Edits made without changing mtime, including
some imports or restores, cannot be detected reliably; repeat a wider scan
when those files need to be reconsidered. This is a filesystem scan, not a
complete event log. Deleted files are absent, with no tombstone record.

`show --json` returns `id`, `title`, `text`, `author`, `time` and `link`, plus
`path`, `folder`, `properties`, `tags` and `links`. `text` is the complete
current Markdown, including frontmatter and original line endings. `title`
is the filename without `.md`. `author` is a non-empty text `author` property,
otherwise null; other author shapes remain in `properties`. It does not
establish the account owner's identity. Tags include frontmatter and inline
tags. Links keep their targets and aliases but remain unresolved: linked
notes, embeds and attachments are never read. `show` reads only the selected
note, so an unrelated note with broken YAML does not prevent that read.

The ID is a SHA-256 of the canonical vault path, a colon, and the percent-encoded
vault-relative note path (forward slashes remain literal). It is stable
through content edits. It is not a content hash or an access token. Moving
the vault or renaming a note changes the ID; replacing a file at the same
path keeps it. Do not infer rename history from this ID. A live citation is
`obsidian:<id>`: remove that initial source prefix before calling `show`, and
pass the saved approved scope separately. An old citation reads the current
file. A missing, moved, inaccessible or out-of-scope file fails clearly;
there is no historical-copy fallback. Comparing its returned time with the
time originally cited can flag a change, subject to the mtime limitations above.

`link` uses Obsidian's [open-by-path URI](https://help.obsidian.md/Extending+Obsidian/Obsidian+URI)
with the absolute path encoded. Returning it does not open Obsidian or grant
access to another scope. JSON goes to stdout; follow-up commands and errors
go to stderr. Exit 0 means success (including an empty changes list), 1 means
the source could not be read completely, and 2 means invalid input or scope.

These commands provide the Obsidian source CLI for REM. The REM caller passes
the user's approved scope, tracks its cursor, and handles unavailable sources.
Nightly collection, live citation routing and the end-to-end audit are part of
the REM integration.

## Create or append a note

Use an existing selected folder and a vault-relative `.md` path. Preview first:

```sh
co obsidian create Course/Plan.md --vault Personal --folder Course --content 'Draft plan'
co obsidian append Course/Plan.md --vault Personal --folder Course --content 'Review complete'
```

Each command prints the selected path, byte counts, proposed text and a `Next`
command containing `--yes --expect <hash>`. Review the preview and copy that
command unchanged to write. `--yes` alone is refused. The hash binds the operation,
canonical vault, selected folders, parent directory identity, target path, input
text and original file version. Changing any of them requires a fresh preview.
An append token cannot be reused after a successful nonempty append.

`create` never overwrites an existing file and never creates parent directories.
Empty content can create an empty note. `append` requires an existing regular,
writable UTF-8 note; it preserves its original bytes and frontmatter. If needed,
it inserts one line break before the added text (CRLF when present in the note,
otherwise LF). Empty append content is a no-op. Symlinks, hard-linked append
targets, excluded directories and paths outside the selection are refused.

After `ls --folder` or `search`, `co obsidian append 1 --content 'Review complete'`
can preview a note row in its saved scope. The confirmation command uses an
explicit vault, folder and note path. A row number with `--yes` is refused;
refresh expired rows instead of guessing their targets.

Each preview or confirmed write uses the vault and folders validated for that
command. If validation detects a redirected path, choose the path again and
run a fresh preview.

For multiline content, pipe UTF-8 input. A terminal with `--content -` but no pipe
is refused rather than waiting for typed input:

```sh
printf '# Plan\n\nReview complete.\n' | co obsidian create Course/Plan.md --vault Personal --folder Course --content -
```

Pipe exactly the same bytes into the printed confirmation command. `--json`
returns a structured preview or result on stdout and puts recovery/next commands
on stderr. Previewing does not create a file, directory, receipt or write cache.
The proposed content is included in the preview; review it before sharing output.

Saving notes is only supported on macOS and Linux.
Unsupported platforms refuse the write; Windows write behavior is not implemented.
A staged file is flushed before publication. Create publishes without replacing
an existing name. Append replaces the target with the complete new file and keeps
its permission bits; inode identity, ownership, extended attributes and ACLs are
not preserved by that replacement. Do not use append when those metadata must be
retained. A nonblocking directory lock serializes these CLI writers, and the
original content and scope are checked again before publication. Pause other
editors or sync tools while confirming, because they can still write to the file
and cause lost changes.
This is not a filesystem transaction against arbitrary external writers.
After an interrupted or failed write, read the target before retrying.

Exit 0 means the preview, write or no-op completed. Exit 1 covers unavailable
files, write failures and stale previews. Exit 2 covers invalid arguments,
missing confirmation or unsafe paths. Recovery stays within the selected scope.
