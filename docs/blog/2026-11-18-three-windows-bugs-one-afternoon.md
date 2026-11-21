# Three Windows bugs, one afternoon

Kim linked a WhatsApp bot on a Windows PC with `co whatsapp listen --phone`.
Pairing worked. Then nothing else did, and every failure came from a
difference that only shows up on Windows.

## The lock you cannot read

The listener holds `listen.lock` with a kernel lock and used to write its pid
inside that file. On macOS and Linux the lock is advisory, so `check` could
still read the pid. On Windows, `msvcrt.locking` makes the locked byte
unreadable to every other process. `co whatsapp check` and `consume` crashed
with `PermissionError` while a listener ran.

The pid now lives in its own file, `listen.pid`. The lock still decides
whether a listener runs. The pid file is only there for people to read.

## The year 57,000

neonize gives a live message's timestamp in milliseconds. Read as seconds,
that is the year 57,000. macOS raises `ValueError` and Windows raises
`OSError 22`. Only the first was caught, so on Windows every incoming message
was skipped as "event not understood". On macOS the same mistake was
silent: every message was stamped with the time it was read, not the time it
was sent.

Timestamps above 10¹¹ are now read as milliseconds.

## cp1252

`consume` pipes each message to a command and sends what it prints. It used
the locale encoding, which on Windows is cp1252, so a reply with a bullet
point arrived as `â€¢`. `consume` now uses UTF-8 in both directions. It also
sets `PYTHONIOENCODING=utf-8` for the command, so a Python script prints
UTF-8 too.

Each fix has a test that fails without it. The Windows tests fake the
platform: one makes the lock file unreadable, one sets the locale to cp1252.
