# The job that would have failed every night

Renaming `co wiki` to `co rem` looked mechanical: about 2,800 occurrences and
232 paths, all in one script. The script ran, and most tests passed. What it
could not see was a file that no search of the repository would ever find.

On a Mac, `co wiki start` writes a LaunchAgent into `~/Library/LaunchAgents`.
Its arguments are spelled out in full: `co wiki --root ~/.co/wiki sync
--scheduled`. That file belongs to the user, not to us. It keeps running after
an upgrade, every five minutes, whatever the command is now called. The issue
said `co wiki` should print the new name and exit 2 in 1.9.x, so scripts break
loudly instead of silently. For a script someone watches, that is the right
behaviour. For a job nobody watches, it means the notebook stops updating on
the night of the upgrade, and the only sign is a log line in
`.state/launchd.log`.

So the rename needed a second half that the mechanical pass could not produce.
The first `co rem` does three things for a notebook made under the old name:

- it moves `~/.co/wiki` to `~/.co/rem` in one `os.rename`, so a failure leaves
  the old folder whole;
- if both folders exist, it refuses and names both, because two notebooks
  cannot be merged silently;
- it removes any job whose arguments point at that notebook, and installs one
  that runs `co rem sync`.

One more gap remains, and the release notes say it plainly: until the owner
runs `co rem` once, the old job keeps waking up to be told the new name.

The script had one more lesson. A search-and-replace that understands prose
also rewrites things that only look like prose. The ignore rule for the nested
GitHub Wiki repository became `co rem/`, and a test's example domain became
`co rem.intranet`. Python files are now rewritten token by token: identifiers
get code rules, and only strings and comments get prose rules. The files that
record history, such as release notes, dated evidence and this blog, are left
exactly as they were written.
