# A Transcript Is Not a Client

The Claude Code Workroom looked much better after we restored its missing
messages. The task was visible, the status said Working, and the conversation
showed both the request and Claude's answer. Then someone asked the question
that the screenshot had managed to avoid: where is the input box?

There was no subtle rendering bug. We had built a transcript and called it a
client. Codex had a direct-message path, so its Workroom could accept a next
instruction. Claude Code stopped at display. The absence was intentional in
the component, but it contradicted the product boundary: a Workroom is the
remote client for the provider session, not a report produced after the session.

Adding a textarea exposed the real complication. A button can look correct
while still sending its text through the outer agent, starting a new task, or
acknowledging a message before Claude has actually started. All three versions
would pass a shallow UI check and lose the conversation the moment a user
relied on it.

We followed the message from the browser back to the native process instead.
The React client sends a provider-scoped request carrying the Workroom's
invocation and observed state revision. The Host accepts it only for an owned
Codex or Claude Code session. For a completed Claude turn, it resumes the same
native session ID. Only after that process starts does the Host acknowledge the
request and publish the attributed user message. The inner provider permission
checks remain in place; recognizing the Workroom does not grant the provider
more authority.

The timing matters. Publishing the user's bubble before process creation felt
responsive, but it could leave the UI claiming that Claude had received words
which never crossed the native boundary. Moving the acknowledgement after
startup made the interface slightly less optimistic and much more truthful.
Stable request-based message IDs also keep reconnect replay from duplicating a
follow-up as though it were the original prompt.

The acceptance test now does more than find an input box. It completes a Claude
Code turn, enters another instruction, verifies that the browser emits
`PROVIDER_INPUT` rather than a new outer `INPUT`, and observes the reply in the
same provider conversation. That is the distinction the first screenshot
missed: a transcript shows what happened; a client lets the user decide what
happens next.
