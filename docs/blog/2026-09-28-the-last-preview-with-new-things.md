# The last preview with new things in it

This morning eight pull requests were open that each added something to
1.8.9: OneNote, watches, web search, Outlook reply-all, WhatsApp Cloud, a
bigger Wiki map, Chromium 154 and a WhatsApp listener fix. Some were three
weeks old. Every one we rebased had drifted: one would have deleted 8,000
lines of main because its commit was a snapshot of the repo from two days
earlier, and another shipped a client for a server that was never deployed.

We had been calling each preview "almost stable" while features kept
arriving. That is how a fix line never ends.

So we drew a line. Everything that was already in a pull request was rebased
onto today's main, fixed until CI was green, and merged into one preview,
1.8.9b19. The drift was fixed on the way: the snapshot PR was rebuilt as the
77 lines it really changed. WhatsApp Cloud was taken back out, because a
command that cannot receive a message should not ship in a stable release.
It returns with its server after 2.0.

From b19 on, 1.8.9 takes fixes only. Anything new, however small, goes to
1.9.

The lesson: a release line ends when you stop adding to it, not when the
list of fixes runs out. Say which preview is the last one with features, and
the stable release has something fixed to converge on.
