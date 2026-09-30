# The pointer the model followed

When we split each co rem Skill into rules and rationale, we left a line at
the top of every rules file: "Why these rules: docs/rem-skills/<name>.md". It
was meant for whoever edits the Skill next, a note to future maintainers that
the history they want is kept elsewhere. It worked: every runtime Skill got
shorter, and a one-page investigation dropped under 15,000 characters.

The 1.9.0a4 acceptance run found the model reading it. Investigating UNSW, one
of its first commands was `sed -n '1,240p'` on
`site-packages/connectonion/docs/rem-skills/rem-investigate.md`. The docs ship
inside the wheel, the Skill named the path, and an agent that is told where
the reasons are will go and read them. The rationale we had moved out of the
turn came straight back in as a file read.

Nothing was wrong with the line. It was written for a person and shown to a
model, and a model treats a path as an instruction to open it. The line now
stays in the repository file and is removed when a turn's instructions are
composed. The model never sees it.

The same run found a second kind of weight the 15k test could not see. A
maintenance turn after a Codex or WhatsApp sync came to 17,534 characters. The
test measured the stage and the page's shape. It did not measure the source
Skill that is appended when the material came from a particular source. But
maintenance after extraction does not read the source at all. It reads the
extraction's notes, and how Codex hides the user's words was the extract
turn's problem. That Skill is no longer appended to it, and the test now
covers every source.
