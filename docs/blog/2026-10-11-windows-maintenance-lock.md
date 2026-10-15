---
description: co rem's maintenance lock crashed on Windows because fcntl is not a module there. The lock now uses msvcrt.locking on Windows and fcntl.flock everywhere else.
tags: [REM, Windows]
---

# The maintenance lock that did not exist on Windows

A Windows user ran `co rem config set` and got a traceback where every
other command just worked. The crash was not in the config logic. It was
one line earlier:

```python
import fcntl
```

`fcntl` is the Unix file-locking module. Python on Windows does not ship
it, so the import raised `ImportError` and the command died before it
could say anything about the user's timezone.

## Two locks, one purpose

REM keeps a maintenance lock so a scheduled tick and a second terminal do
not write the same notebook at once. There are two halves. `_THREADS`
serialises threads inside one process; `_file_lock` is the half other
processes see, and the one whose whole existence is a file carrying an OS
lock. On POSIX that lock is `fcntl.flock`. On Windows it has to be
something else.

The repository already knew this. `network/host/schedule.py` holds the
same shape of lock and branches on `os.name`:

```python
if os.name == "nt":
    import msvcrt
    handle.seek(0)
    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
else:
    import fcntl
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
```

`_file_lock` just never got the Windows half. The fix was not to invent a
new lock; it was to port the pattern already proven one directory over.

## What msvcrt will not do for you

The port had two small traps. `msvcrt.locking` refuses to lock an empty
file, and the maintenance lock file is created empty, so `_try_lock`
writes a single null byte first and seeks back to zero. And a busy
`msvcrt` lock is reported as a plain `OSError` (`EACCES`/`EDEADLK`), not
the `BlockingIOError` that `fcntl.flock` raises — so those two errnos are
translated back to `BlockingIOError` and the existing retry loop is
untouched.

## What I could not verify

I developed this on Linux, so the POSIX path is what I actually ran: a
second holder is refused and the lock is re-acquired after release. The
Windows path I could only read, not run. The CI matrix already builds on
`windows-latest` and runs a `windows-e2e` job, so Windows behaviour is
exercised there rather than by me. That asymmetry is the part of this
change I am least sure about, and if it is wrong, `co rem` on Windows
fails to lock at all — the same crash, one layer up.
