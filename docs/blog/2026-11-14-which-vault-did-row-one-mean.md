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
