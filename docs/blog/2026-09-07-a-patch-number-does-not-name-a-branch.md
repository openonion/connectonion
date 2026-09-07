# A Patch Number Does Not Name a Branch

Draft for the 1.8.4 release process.

The readiness review reached a strange instruction: before a pull request
could land on `main`, it needed an issue promising to carry the change forward.
Forward to where? The change was already aimed at the newest line.

At first this looked like another missing metadata field. Several PRs had
release estimates in prose that the workflow could not parse. Those needed
the exact field names. This failure survived that correction. The workflow
parsed 1.8.4, saw a nonzero patch number, and required a forward-port tracker.
It never checked the destination branch.

Creating an issue would have made the expression happy. It would also have
left someone responsible for work with no destination. The rule had a valid
origin: a fix on an older maintenance line must reach the active newer lines.
The version string had become a shortcut for deciding whether that situation
existed, and 1.8.4 on main exposed the difference.

The correction keeps the obligation where there is somewhere to port from:
a patch aimed at a maintenance branch. Mainline and stacked feature work still
need their release metadata. A regression runs the actual workflow JavaScript
with both kinds of destination, including a maintenance PR with a closed or
unlabelled tracker. Narrowing the trigger must not make those cases disappear.

CI then caught a smaller surprise in the documentation. The release checklist
scanner interpreted the example branch names `release/1.7` and `release/1.8`
as files a releaser should edit. It too had collapsed two different meanings
into one string. The scanner now recognizes that explicit branch-name pattern
while continuing to check the real release files.

Both failures could have been silenced by changing what the text happened to
look like. Keeping the distinction in the checks makes the next release easier
to reason about: a version names the artifact, a branch names where the change
is going, and a forward-port issue names work that still has a destination.
