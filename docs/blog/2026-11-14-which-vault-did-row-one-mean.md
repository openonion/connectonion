# Which vault did row 1 mean?

*2026-11-14*

During a terminal walkthrough, `co obsidian` found two vaults with the same
name. Their paths made them easy to tell apart in the list. The suggested
command used the name again and failed. We could browse each vault by
typing its full path, but the very next prompt already had enough
information to carry forward the choice.

The vault list now offers row numbers. Folder browsing can reuse a short
name when it uniquely identifies the selected vault. With a duplicate name,
the suggested command carries the path. Inside a folder, repeated filenames
show a parent path, and the suggested read command carries the list ID so it
can find the same note after another list changes the row order.

That distinction matters more for a write. An append preview can start
from a number. Its confirmation names the exact file and includes a hash
of the original version and requested change. If the file changes while
the preview is on screen, an old confirmation is refused. A preview can
stay on screen while the person who asked for it keeps editing.

The CLI tests use temporary vaults to check duplicate names, reads from an
earlier list, and the outcome of confirming a preview after a note changes.
They also check that creating a note never overwrites an existing file.

## A saved note is evidence

REM registers each vault and its selected folders separately. Registration
saves the paths. Approval precedes synchronisation, which records each changed
Markdown note as a version in a per-vault inbox under the notebook's source
configuration. A rerun with the same bytes adds no new version. The queue
checkpoint tracks which versions reached maintenance, so a failed model call
can be retried against the already saved snapshot.

The alternatives were to reopen the live note for every investigation or to
put all vaults in one file namespace. A live link would change what an old
citation means. A shared namespace would collide when two vaults both contain
`Course/Meeting.md`. Versioned inboxes keep the citation tied to the saved
note even when its live text changes. Investigation uses the currently
approved selection, including its removal rules.
