# A warning that was not for us

Checking OneNote on a clean Python 3.10 install of 1.8.9b19, the first thing
on screen was not OneNote. It was two lines from a Google library: a
FutureWarning that it will stop supporting Python 3.10 on 2026-10-04, followed
by the line of its own source that raised it. Every command that loaded a
Google tool printed them, above its own answer, and `co onenote` loads one
through the tools package.

Nothing about it was wrong. Python 3.10 does reach end of life, and the
library is right to say so. But the notice is addressed to whoever maintains
the dependency pins, and it was landing on someone who asked for their
notebooks. They cannot act on it mid-command, and a CLI whose first two lines
are noise teaches people to skip the first two lines.

So the CLI now filters that one warning, by module, as it starts. Every other
warning still shows, ours included, and a test checks both halves. Whether we
drop Python 3.10 is a decision for our own release notes, made on our own
schedule.

The lesson: a dependency's message to its maintainers is ours to read and
act on, not to pass through to every user on every command.
