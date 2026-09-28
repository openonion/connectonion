# Ten students, ten new threads

Last week the owner answered capstone emails from about ten students. Most of
them had written as a group: one student sends, the rest of the team sits on
To or Cc. The agent answered each one with `co outlook reply`, and the answer
went to the student who pressed send and nobody else.

The agent noticed, and did what looked sensible: it wrote the answer again
with `co outlook send`, every teammate on the To line, "Re:" in front of the
subject. The students got it. They also got it as a new conversation. Gmail
and Outlook thread by the message headers, not by the subject, so each team
now had two threads about the same project, one with the question and one
with the answer, and the next reply from a student went back to whichever one
they happened to open.

Nothing had failed. Each command did exactly what it said. `reply` was built
to answer the sender, and when someone needed copying we had already added
`--cc` to it, so a person could be looped in without leaving the thread. That
fixed "add Sam". It did not fix "answer everyone who is already here", which
is the more common case on a group thread, and the one that pushed the agent
back to `send`.

Graph has a separate action for that, `replyAll`, and a matching
`createReplyAll` for a reply scheduled with `--at`. `co outlook reply --all`
uses them. We sent a test mail to two addresses and replied to it with
`--all`: both recipients kept, same conversation in Outlook, one thread on
the Gmail side.

One detail came up while wiring `--cc` into it. Setting the Cc on `replyAll`
replaces the list Graph worked out, it does not add to it. So we read the
original Cc first and keep it. The first version kept all of it, including
the owner whenever they had been on the original Cc, which on a group thread
is where they usually are. Graph leaves you off your own reply-all; copying
the list back by hand has to do the same.

The lesson is about workarounds. When an agent reaches for `send` with "Re:"
in the subject, the tool is missing a verb, and the workaround will look fine
from the sender's side every time. It only looks wrong in the recipient's
inbox, which is exactly where we were not looking.
