# Bind first, then prepare

A daemon that loses a startup race was deleting the winner's credentials.

Two `co browser` commands in two terminals, cold, at the same moment: both
spawn a daemon, and both race for the same socket. That race is old and handled
— an exclusive lock on `<sock>.lock`, held for the daemon's lifetime, and the
loser calls `sys.exit(0)` the moment it cannot take the lock. The winner keeps
the socket; the loser goes away. This has been true and tested for a while.

What changed under it is that a private remote-browser daemon now starts a
gateway and writes a proxy-credential file before it serves. And the startup
did that *first*:

```python
await self._prepare_runtime()   # start gateway, write proxy-auth.json
self._bind()                    # take the lock, or sys.exit(0)
```

The credential's path derives from the shared profile directory, so both
daemons write the *same file*. The loser wrote its own credential — for its own
gateway, with its own password — on top of the winner's. Then it lost the lock,
exited, and its `finally: _shutdown_async()` did the tidy thing: removed the
proxy-credential file it had created.

Except the file is shared. It removed the winner's.

The winning daemon is now serving on its socket with a live gateway whose
credential is gone from disk. Every page command comes back `407`. Nothing
logged an error; nothing points at the loser, which exited cleanly a moment ago
having done exactly what its shutdown path says to do. The daemon that owns the
socket just stops working, for a reason that isn't in front of it.

The fix is one swap:

```python
self._bind()                    # take the lock, or sys.exit(0)
await self._prepare_runtime()   # only the winner gets here
```

The loser now exits at the lock, before it has written or started anything, so
there is nothing for its shutdown to remove. `_prepare_runtime` runs only for
the daemon that won the socket.

The regression test holds the singleton lock itself — standing in for the live
winner — writes a credential, then runs a second daemon's `serve_async` and
asserts two things: it exits 0, and the credential on disk is byte-for-byte the
one the winner wrote. Reinstate the old order and the test reddens: the loser
reaches `_prepare_runtime`, and the winner's bytes are gone.

The bug was not in the race handling, which was careful. It was that a cleanup
path written for one daemon's private file ran against a file that had quietly
become shared, because a later feature put the write before the thing that
decides whether this daemon is allowed to write at all.
