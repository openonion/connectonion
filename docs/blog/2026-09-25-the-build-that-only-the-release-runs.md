# The build that only the release runs

1.8.8b10 passed 48 checks, merged, and was tagged. Nine minutes later the
release workflow failed, and nothing reached PyPI.

The release builds the package the way a user's pip would meet it: first the
source archive, then the wheel from inside that archive. No other check does
that. The unit tests read the repository, and the slow wheel test builds
straight from the checkout, where every file is present.

Earlier the same day, a fix had stopped shipping internal design records: a
tester found planning notes and design history inside every new project's
`.co/docs/`, and the exclude list grew to leave them out. It left them out of
the source archive too. But `co ai`'s prompt library does not copy those
records; it links to them, with symlinks into `docs/`. In the checkout the
links resolve. In the archive, eighteen of them pointed at files that were no
longer there, and the wheel build stopped on the first one.

The fix is small: the eighteen links are gone, because the records they led to
are internal by decision. The lesson is in the test that comes with it. It
does not build anything, which would be slow; it walks every symlink inside
the package and asks whether its target ships. A link to a file the package
leaves out is exactly the failure that only the release build used to find.

The tag for 1.8.8b10 stays where it is: tags are not moved. The same changes
ship as 1.8.8b11.
