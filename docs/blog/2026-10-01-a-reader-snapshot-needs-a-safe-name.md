# A reader snapshot needs a safe name

The REM reader is a single HTML file. `co rem open` renders the private notebook
into a temporary snapshot and asks the browser to show it. That final write
failed on Windows before the browser opened: the code asked for `O_NOFOLLOW`, a
POSIX flag Windows Python does not have.

The flag was there for a reason. The snapshot name is predictable, so opening
that name directly could follow a planted symbolic link and overwrite its
target. Dropping the flag would make Windows launch while losing that safety
property.

The writer now puts the complete page in a private, randomly named file in the
same temporary directory, then atomically replaces the public snapshot name.
Replacing a directory entry does not open the old entry's target. A visible
symlink is still refused, and a link planted between the check and replacement
cannot redirect the write. The temporary file is removed if any step fails.

This also gives the browser a complete new snapshot rather than a partially
rewritten old one. The test covers a planted link, a repeat open, and an
environment without `O_NOFOLLOW`. The Windows CI run is the final platform
check before the next preview.
