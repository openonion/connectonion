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

Two costs were found and cut on the way. Building the command tree once per
check made a full audit take 1 minute 43 seconds. Building it once per run
takes 17. And because a model's verdict varies between runs, it never blocks
a merge: the rules gate every PR, and the review writes its suggestions to
the job summary for the pages that PR changed.
