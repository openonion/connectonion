# The skill that knew the rules but not the test

`cli-skill-design` is the skill an agent loads before it adds a `co` command.
It already argued the right things: help is the usage skill, every command
names its next step, and errors say how to recover. What it did not know was
that CI now checks every page. A skill that describes the principle but not
the check is how you end up with a PR that follows the spirit, fails the
gate, and then gets fixed by guessing what the gate wanted.

So the skill now opens with the contract as CI enforces it. Every page needs
an example whose flags exist, and one of fifteen fixed words saying what the
command changes. The way back to the parent is generated, and the skill tells
you not to write it. It lists the commands to run before pushing, including
the run with CI's colour codes on, which has already broken two of our own
help tests.

It also carries what the audit taught. Write "what it changes" from the
handler: that is how we found that `co auth feishu` creates an application
its help never mentioned. Put the reader's own word in the first line: a
model searching for "credit balance" opened `co status` and left, because
the page said "account status". When you add a command group, add a goal to
the discovery test, and never truncate the help pages you feed it. Our first
harness did, and four of its "failures" were its own.
