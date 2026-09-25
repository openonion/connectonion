# The right page was already open

The audit of our help pages included a test for agents. A model got a goal,
such as "let another agent call mine", and could read only the help pages it
asked for. It had to name one command. It failed four goals, and in every one
it had already opened the page that answered it.

"Check how much credit my account has left" went to `co status`, which read
"Check credential sources, account status, and deployments." Balance is
printed by that command and was not mentioned in its description, so the
model moved on. "Let another agent call mine" reached `co trust add`, which
said "Add address to contacts (default) or whitelist" and nothing about what
a contact is allowed to do. "Set an API key that all my projects use" reached
`co env set`, which said "the selected file". The fact that the default file
is the shared `~/.co/keys.env` was one level up, in parentheses. And
`co skills` and `co sub` never said which of them was for someone else's
published skills.

The fix was not a new command. Each page now says the thing the reader came
for, in the words they would use: your credit balance; who may call your
agent; the file every project reads; another person's published skills. After
the change the same test finds 13 of 13 single-step goals.

Two goals still fail by design, and the test says why. Writing a new skill
and adding someone's published skill to a project each take two or more
commands. The test accepts one, so both are marked expected failures with the
reason written down. The help for the second now names the other step:
`co sub sync` ends by saying how to ship one of those skills with this project.
