# Rules first, then judgement

`co audit` began as a question: can one command tell us whether every `co`
help page is something an agent can act on? The first draft leaned on a
model. It walked the help pages from `co --help` and tried to find each
command, which is a fine test, and an expensive and noisy way to learn things
a regular expression already knows.

The maintainer's correction was simple: check everything that can be checked
by rule first, and use the model only for what needs judgement. Most of the
contract turned out to be rules. Does `--help` exit 0 and write nothing? Is
there an example, does it run this command, does every flag in it exist?
Does the page say what it changes? Does every group list all of its
children? That last rule quietly replaced the model walk. `co --help` is a
group page, so if every group lists its children, every command is reachable
from the top, and that can be proved without asking anyone.

What is left for the model is what a rule cannot see. Is the first line clear
to a newcomer? Does "what it changes" match the command? Would anyone actually
run the example? Is the page simple? On its first run it flagged `co trust add`
for saying `trust='strict'`, which is our code's spelling and not a reader's.
No regular expression would have caught that.

The last correction was about where the rules look. The first engine read the
command registrations in the source. The maintainer asked why: just run `co`
and judge what it prints, because that is all an agent ever sees. The
rewritten audit does exactly that. It starts `co --help`, opens every command
the page lists, and walks down, then compares what it reached with the full
list `co commands` prints. The first run found two things the source-based
check had passed. `co --help` itself had no example. And `co proxy`'s label
lived in a docstring that its hand-written help never prints. An agent could
not see either. Now the check cannot either.

Then one more: why is `co audit` only for `co`? The question it asks, whether
an agent can use a tool from its help alone, is the same for `gh` or `yt-dlp`.
So there is one set of rules and one code path, and the command takes what you
would type: `co audit co gmail`, `co audit gh`. Our own conventions, like the
fixed "what it changes" words, stayed in our CI test rather than in the tool.
Pointed at `gh`, it found that reading any help page writes a device id to
disk, and that 101 of 228 pages have no example; `uv` has none on any of its
45 pages.

A model's verdict varies between runs, so it never blocks a merge. The rules
gate every PR, and the review writes its suggestions to the job summary for
the pages that PR changed.
