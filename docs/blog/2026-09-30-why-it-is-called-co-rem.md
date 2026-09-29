# Why it is called co rem

On 25 September the owner ran `co wiki init` on his own accounts. It took ten
and a half minutes and wrote a 15,498-line log. At the end there were 370
people pages, 138 organisation pages and 24 project pages, and every one of
them was an empty frame that said `Investigation: not started`.

Nothing had gone wrong. That is what init is for: it maps who you write to and
which projects you work in, without running a model. The pages fill in later,
when the notebook reads a person's mail or a project's sessions and writes
down who they are and where you left off. Most of that happens in the
scheduled runs, and the default schedule starts at three in the morning.
Nobody watches it. You find out afterwards that a page has filled in.

The name hid that. A wiki is something people write, and this one has no edit
button on purpose. The reader is read-only and the AI is the only writer. What the feature does is closer to sleep. In REM sleep the
brain replays the day and keeps what matters. It does not store the day
whole; it decides what to keep and connects it to what was already there. The
notebook does that for your work. A thread with a partner becomes the terms
you agreed and the one question still open. A week of sessions in a
repository becomes where the project stands.

So in 1.9.0 the feature becomes **co rem**, always with the `co`. On its own,
"rem" is a CSS unit, a band, and the comment keyword in Windows `cmd`. It is
not an acronym.

A new name does not make anything cheaper, so the limits stay as they are.
Today the command is still `co wiki`, labelled Experimental in 1.8.9. A quick
first pass of your own page took eight to nine minutes in our runs. One very
large subject cost 8.2 million tokens over three and a half hours, which is
why investigation is moving to searching the saved mail instead of
summarising all of it (#1850). The rename is scheduled last, as one mechanical
change after the first-run work in #1943. The empty frames come first: a name
about the night's work should arrive after the first morning has something in
it.
