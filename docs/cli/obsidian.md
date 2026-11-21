# Obsidian notes from the terminal

`co obsidian` discovers local vaults and lists, reads and searches Markdown
notes in selected folders. The commands run offline without a model.
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
