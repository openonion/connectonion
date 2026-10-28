# The diff that was not UTF-8

`co handoff send` is supposed to package what you changed and ship it. On a
repository whose working tree still held Latin-1 bytes in an old file, it never
got that far: collecting the code patch called `git diff`, then decoded the
bytes as UTF-8 the hard way, and Python raised `UnicodeDecodeError` before any
preview or send could run.

Nothing about the patch was wrong. The assumption was. Git will happily print
whatever is on disk; `_git_out` treated every byte sequence as valid UTF-8.
One non-UTF-8 line in an otherwise fine diff killed the whole handoff.

The diff is read as bytes and kept with `surrogateescape`, so a Latin-1 line
stays those bytes on the way to the recipient. Accept writes the patch back
with the same encoding, and `git apply` puts the original bytes on disk.
Collecting the diff still does not raise. A unit test applies the patch and
checks the resulting file byte for byte.
