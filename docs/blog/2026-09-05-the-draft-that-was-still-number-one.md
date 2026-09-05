# The draft that was still number one

The Gmail draft workflow looked straightforward: list drafts, choose a number,
attach a file, and preview before sending. The first discoverability test found
that the piped listing did not print row numbers. Given only that output, the
model chose `co gmail draft preview 0`. Numbering the output fixed that test.

A second audit found a quieter problem. If a later listing returned no drafts,
the command printed “none” but retained the previous numbering cache. Row one
could still resolve to a draft from an earlier listing. The screen and the
command disagreed about what “one” meant.

An empty listing now clears those numbers. The skill also tells the reader to
use the ID printed by draft creation, or list again before choosing a number.
Creating a draft does not make it row one. That distinction matters when the
next command changes attachment state.

The same audit followed the send prompt to its less visible exit. Answering
“no” already kept the draft and printed a preview command. Ending input or
interrupting the prompt needed the same recovery path. Those cases now exit
with code 1, retain the draft, and name the command to inspect it again.

The focused suite passes 241 tests, including regressions for stale numbering
and all three interruption signals. Two text-only tip tests gave a fresh model
only synthetic output and a goal. It chose the existing create command after
an empty listing and the exact preview command after an interrupted send.
Neither test had access to a mailbox or a shell.

The useful question turned out to be what the next caller can infer from the
last output. A command can report a true result and still leave behind state
that makes the next action wrong. Testing that transition caught what checking
each success message on its own had missed.
