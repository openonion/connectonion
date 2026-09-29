# A snapshot must not follow a detour

*2026-09-29 · Design Journal*

`co wiki open` writes a disposable HTML snapshot beside the operating system's
temporary files. That sounds like a harmless last step: the notebook has already
been read, the HTML has already been rendered, and the browser only needs a
file to open. On Windows, it was the step that stopped the command before the
browser could see anything.

The Unix implementation opened the predictable snapshot name with
`O_NOFOLLOW`, then made the file private with mode `0600`. Those are useful
properties, not decoration. A predictable temporary filename must not become a
way for a planted link to redirect a private notebook snapshot into another
file. Windows Python does not expose `O_NOFOLLOW`, and Windows uses ACLs rather
than POSIX mode bits, so importing the Unix expression unchanged made the
reader fail before it wrote its local page.

The tempting repair was to replace the missing flag with zero. That launches
the reader, but it also quietly changes the security promise: Windows would
follow an existing symbolic link and truncate its target. A portability fix
that turns a refusal into an overwrite is not a fix.

The reader now uses Windows' `CreateFileW` with
`FILE_FLAG_OPEN_REPARSE_POINT`. It receives a handle to the reparse point
itself, inspects that handle, and refuses to truncate it. A regular file is
rewound and truncated only after that check. POSIX keeps its existing
`O_NOFOLLOW` path and its `0600` mode. Each platform therefore has the same
observable rule: the disposable snapshot is written to the named file, never
through a detour to a target chosen by someone else.

The test suite now separates the shared guarantee from platform mechanics.
Windows checks that the reader can write without POSIX flags or modes; POSIX
continues to assert mode `0600`. The planted-link test still runs wherever a
machine may create symbolic links. On a standard Windows account without
Developer Mode or elevation, that setup is unavailable and the test reports an
explicit skip rather than pretending the security path was exercised.

The lesson is small but reusable: a missing filesystem flag is not merely an
API compatibility detail. First name the invariant, then use the platform's
own primitive to preserve it. For a private local snapshot, “opens on Windows”
is not enough; it must still open the file the application intended to write.
