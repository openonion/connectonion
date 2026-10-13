# Wait for the answer

*2026-10-13*

On 1.9.2b21, the recipient's agent opened a handoff, found the folder empty,
and asked the sender for the code. Then it checked once, saw no answer yet, and
reported itself blocked. The answer arrived ninety seconds later, because the
sender's machine answers when it next checks its inbox.

An agent that stops when an answer is merely late leaves the person to notice
and start it again. The turn that does the work now keeps
`co handoff status <id> --wait` running until the answer comes, and searches
the sender's session copy before it asks anything. The inbox also names the
sender by the name their handoff carries, not their mailbox.
