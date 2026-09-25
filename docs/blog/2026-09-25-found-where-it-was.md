# Found where it was

Yesterday's post ended on a scheduled job that could not find the daemon a
login shell had started. The two worked out the socket address from environment
variables, and cron had none of them. We fixed it by filling in the blanks: when
`$XDG_RUNTIME_DIR` was missing, use `/run/user/<uid>`, which is where it would
have pointed; on a Mac, ask the OS for the per-user temp dir instead of trusting
`$TMPDIR`. A login shell and a cron job now agreed. The tests passed.

Then we went looking for the next shell that would disagree, and there were
plenty. `/run/user/<uid>` only exists while systemd-logind thinks you have a
session. Log in at the desktop and it is there. `ssh` in on a box without
`pam_systemd`, or `su` to the user, or open a shell in a container, and it is
not. So the same person on the same machine got `/run/user/1000/co/browser.sock`
from one terminal and `/tmp/co-onion/browser.sock` from another. The second
terminal started a second daemon, which launched Chrome against the profile the
first one was holding. And `co browser close` from that terminal closed the
daemon it could see, never the one that was actually running.

The Mac had the same problem the other way round. The fix ignored `$TMPDIR`, so
anyone whose profile set it (or whose shells did not all agree on it) had a
daemon from before the upgrade under `$TMPDIR/co-<user>/`, and the upgraded
client looked somewhere else.

The lesson we should have taken the first time is that the fallback was never
the problem. Reading the session at all was. Which variables a process has
depends on how its user got there, and that is exactly what must not change the
answer. So the address no longer reads any of them: `/tmp/co-<user>/` on Linux
and the OS's per-user temp dir on macOS, 0700, a chmod that fails loudly if
someone else made the directory first. Only `$CO_BROWSER_SOCK`, which somebody
sets on purpose, still moves it.

Moving the address creates its own version of the bug: every daemon already
running is now at an old address. So a client first checks the stable one, and
if nothing is running there it looks at each place an older version used. It
follows one only if a live owner pid is recorded beside the socket and the
directory is ours and closed to everyone else. That last check matters because
the client never created those directories; without it another local user could
plant a socket where an old client used to look. Once that old daemon closes,
the next one starts at the stable address, and the old places stop mattering.

Two smaller things turned up on the way to `close`. On a headless Linux box,
`co browser --no-headless close` was refused with "needs a display", which is
true of opening a window and not of shutting one. A script that always passes
the same flags had no way to stop its browser. Now close, and `tab close`, go
through whatever the display flags say. And the close path reads the process
table from `ps -o lstart`, which prints dates in the user's language. On a
Korean or Japanese desktop the start time is not five English words, the parse
put half the date into the process name, and close found nothing to wait for.
`ps` now runs with `LC_ALL=C`.

None of this showed up in yesterday's tests because they all ran in one kind of
shell. The new ones make the machine up: a fake `/tmp`, a fake `/run/user`,
`$XDG_RUNTIME_DIR` set and unset, `/run/user/<uid>` there and gone, a `TMPDIR`
pointing somewhere else, and a `ps` that answers in Korean unless it is asked
for C. The address has to come out the same in every one of them.
