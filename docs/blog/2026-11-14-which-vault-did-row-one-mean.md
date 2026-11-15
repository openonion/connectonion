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

The list ID carries the vault and folder selection as well as the row.
A new listing can have its own row 1 without changing what the earlier
read command points to. When the list expires, the terminal asks the user
to list again or pass the note's path.

The CLI tests use temporary vaults to check duplicate names, reads from an
earlier list, and the scope used to resolve links. A note outside the
selected folders does not contribute a path or make the selected folder fail.
