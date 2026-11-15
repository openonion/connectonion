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
their names, paths, availability and open status. `Next` fills in the first
available row for `co obsidian ls`. A unique vault name or path also works
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

For multiline content, pipe UTF-8 input. A terminal with `--content -` but no pipe
is refused rather than waiting for typed input:

```sh
printf '# Plan\n\nReview complete.\n' | co obsidian create Course/Plan.md --vault Personal --folder Course --content -
```

Pipe exactly the same bytes into the printed confirmation command. `--json`
returns a structured preview or result on stdout and puts recovery/next commands
on stderr. Previewing does not create a file, directory, receipt or write cache.
The proposed content is included in the preview; review it before sharing output.

Actual writes currently require macOS or Linux with POSIX directory handles.
Unsupported platforms refuse the write; Windows write behavior is not implemented.
A staged file is flushed before publication. Create publishes without replacing
an existing name. Append replaces the target with the complete new file and keeps
its permission bits; inode identity, ownership, extended attributes and ACLs are
not preserved by that replacement. Do not use append when those metadata must be
retained. A nonblocking directory lock serializes these CLI writers, and the
original content and scope are checked again before publication. External editors
or sync clients need not honor that lock: pause concurrent edits while confirming.
This is not a filesystem transaction against arbitrary external writers.
After an interrupted or failed write, read the target before retrying.

Exit 0 means the preview, write or no-op completed. Exit 1 covers unavailable
files, write failures and stale previews. Exit 2 covers invalid arguments,
missing confirmation or unsafe paths. Recovery stays within the selected scope.

This feature does not add REM collection or multi-vault subscriptions. The CLI
reader foundation is #3039; the separate single-vault REM draft is #3064.
