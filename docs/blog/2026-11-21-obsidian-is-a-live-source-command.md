# An Obsidian citation should open the note that exists now

*2026-11-21 — design candidate for PR #3064*

The earlier Obsidian REM proposal copied note bodies into a source store and
connected them through a shared Python hook registry. It could reopen a saved
version, but it also gave REM another store to manage and every new source
another interface to implement. The discussion in
[#3249](https://github.com/openonion/connectonion/issues/3249#issuecomment-7057792487)
changed the target: the source owns its content; REM keeps a read cursor and
asks the source's command for live material.

The replacement is two commands. `co obsidian changes --since … --json`
checks filenames and modification times in the folders the user selected.
`co obsidian show <id> --json` opens one current note and returns its text,
properties, tags and links. Both require an explicit folder selection. A
valid ID cannot enlarge it, and a link inside a note is not another read.
The JSON envelope and core item fields follow Asana's CLI proposal in
[#3060](https://github.com/openonion/connectonion/pull/3060).

The ID combines the vault path's hash with the relative note path. Editing
the body leaves it stable, so `obsidian:<id>` can refer to the same location
on the next read. Moving the vault or renaming the file changes the ID. A
deleted file fails; it is not replaced by an old copy. This gives up historical
reproduction on purpose. It also means a reused path refers to the new file
at that location, rather than to an invented persistent document identity.

Modification times make the incremental command small and independent of
Obsidian's process. They are not a complete change history. Boundary items
can repeat, deletions have no tombstones, and edits that preserve timestamps
can be missed. The response captures an upper time bound before the scan so
the caller can repeat safely after a failure. It must advance its cursor only
after processing the result, using the same approved folders.

The source metadata is useful beyond person pages: tags and links can support
matching, folders and project properties can locate project context, and the
body can provide knowledge or decisions. None of those signals proves that a
statement belongs to the user. The source guidance keeps that distinction
explicit while leaving the output format to each REM stage.

This candidate removes the old hook and snapshot implementation from #3064.
It does not wire the generic REM stages to the new CLI. Tests are provided for
incremental windows, current reads, scope refusal, malformed input and output
streams; they must be run on the candidate before submission. The later generic
integration still needs clean-install, nightly-stage, live-citation, cost and
failure-isolation evidence. Earlier snapshot demonstrations cannot stand in
for that evidence.
