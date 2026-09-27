# The directory it started in

The fix was in the release: a listener now remembers which version it
started with, and after an upgrade it restarts itself into the new code. We
installed 1.8.9b16 on the owner's Mac and ran the check. It said the old
listener predated version tracking, exactly as designed. We ran `co whatsapp
listen --restart`, and it said the new listener "runs 1.8.9b17; 1.8.9b16 is
installed".

No 1.8.9b17 existed anywhere except on the branch we were preparing it on.

The listener is started as `python -m connectonion.cli.main`, and `-m` puts
the current directory at the front of Python's search path. We had run the
command from inside the repository, so the listener loaded the source tree
it happened to be standing in, not the package pip had installed. Worse, the
restart this release added would have compared "running b17" with "installed
b16", restarted, landed in the same directory, and done it again every minute.

That is not a mistake only a developer makes. Anyone who clones the
repository, or keeps a folder called `connectonion` in their home directory,
gets the same thing.

The fix does two things. The listener now always starts in its own inbox
directory, where there is nothing to import by accident. And a restart is
tried once per installed version: if the versions still disagree afterwards,
the listener says so in its log and stops trying.

The lesson: an end-to-end test earns its name by running the way a user
runs, including from the wrong directory. This one ran from exactly where the
developer was standing, which was the wrong place.
