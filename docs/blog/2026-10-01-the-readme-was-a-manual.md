# The README was a manual

Someone landing on github.com/openonion/connectonion gets about ten seconds
to decide whether this is a project they can trust. Our README spent those
seconds badly. It ran to 1,179 lines. Near the top sat a badge that read
"Status: Production Ready", which we had awarded ourselves. Under the demo GIF
was a caveat that `co search` was "in the 1.8.9 preview", written before 1.8.9
went stable and left there after 1.8.10 shipped. Further down were two FAQ
sections answering the same questions in slightly different words, and eight
links to Discord. One of those was a badge pointing at server 1234567890, a
placeholder ID that had never rendered anything.

None of it was written carelessly. Each section was true on the day it was
added. The page grew the way a notes file grows: every release added a
paragraph, and nothing ever took one away. The new pitch, that `co` is a
harness any agent with a shell can use, sat on top of an older SDK reference
covering system prompts, log files, iteration limits, class-based tools, the
project tree and how to run the tests. A visitor had to read past the second
to be sure the first was the point.

The obvious fix was to delete. The catch was that the deleted text was
documentation, and some of it existed nowhere else. So before any section
left, we looked for the page under `docs/` that already taught it. Most had
one: prompts, iteration limits, logging, plugins, hooks, `@xray`, trust and
hosting each have their own page, usually more current than the README copy.
Three did not. The repository tree moved into CONTRIBUTING.md, where
contributors actually look for it. The paragraph on the default model and the
free fallbacks moved into the models guide. The plain-language explanation of
`co rem` moved to the top of its command reference. The README now links to
those pages instead of repeating them.

The second rule was that a badge has to report something, not claim it. The
"Production Ready" badge went. In its place are badges that a service fills
in: the version on PyPI, the Python versions PyPI lists, the result of the
real `Tests` workflow on main, the license and the download count. If the
tests go red, the badge goes red with them. That is the point.

Every command on the new page was checked against its own `--help`, on this
checkout and on a clean install of 1.8.10 from PyPI, before it went in. That caught one claim we
had been about to make. We wanted to say that every write previews first, but
`co gmail send --help` says it sends immediately, without a preview. So the
page says what is actually true: each command's help states whether it is
read-only or what it changes, Calendar, YouTube and Linear writes preview
until you confirm, and `co ai` asks before a risky tool call.

The README is about 160 lines now. It tells you what ConnectOnion is, gets a
command running in five lines, shows it working, and sends you to the docs
for everything else. The two files a careful evaluator checks next,
SECURITY.md and CODE_OF_CONDUCT.md, exist now as well. While writing the first
we found that GitHub's private vulnerability reporting is still turned off
for this repository, so the policy explains what to do until it is on.

What the work teaches is mostly about upkeep. A front page drifts like any
other page, and the parts that go stale first are the hand-written ones:
version numbers, preview notes, status claims. Those are the parts that make
a reader stop trusting the rest.
