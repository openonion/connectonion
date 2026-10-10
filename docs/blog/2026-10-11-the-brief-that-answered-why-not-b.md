# The brief that answered "why not B?"

A handoff fails at one moment. The new person, or their agent, asks why the
obvious other option was not taken, and the only one who knows is the person
who just handed the work away.

So every test of `co handoff` ended with that question. Eight times we
discussed a small task with Codex on one machine, decided between two options
and rejected one for a reason, then handed it over: four times from a Mac to a
Linux box, four times back. Each time the receiving machine opened a fresh
Codex session from the brief and was asked why option B was rejected, plus two
other questions only the conversation could answer. Every answer came from the
brief. One of them was "Option B used in-process retries; because the app
deploys several times a day, restarts would lose pending retries", which was
the reason given an hour earlier on the other machine.

What made that work was mostly a section heading. The brief has a "Rejected"
section, with the reason for each dropped option, because that is the question
a newcomer asks first and the one a summary leaves out. The rest is plumbing
with the safety turned up: a preview of exactly what leaves, refusal of keys
and invite codes, a content hash so the approved text is the sent text.

Compaction nearly broke it. Claude Code keeps a readable summary when it
compacts a long session. Codex encrypts its summary on disk; across 107
compactions on one machine, none could be read. What Codex does keep in the
clear is everything the user typed, and that turned out to be enough to
reconstruct what was decided.

One problem is still open, and we'd rather say it here than have someone find
it. An agent running in full-auto can read the preview and approve it itself.
Text in a command's output cannot stop the agent reading it, so the approval
has to come from somewhere the agent cannot reach. That is the next thing to
build.
