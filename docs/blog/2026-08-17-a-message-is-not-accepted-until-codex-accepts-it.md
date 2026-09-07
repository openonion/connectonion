# A Message Is Not Accepted Until Codex Accepts It

The new Work Room composer looked simple: type a follow-up, press Enter, and
keep talking to the same Codex thread. Its first implementation had a subtle
lie. Host put the text in a mailbox and immediately acknowledged it. The browser
cleared the draft. If the native turn completed before Codex drained that
mailbox, the message had never reached Codex and the one recoverable copy was
already gone.

Calling that acknowledgement a success confused two different facts. A mailbox
enqueue says that ConnectOnion accepted responsibility for a message. It does
not say that the native provider accepted the message. The same difference
appears after a terminal turn: starting a worker says nothing about whether
`thread/resume` and `turn/start` will succeed.

We considered keeping the fast acknowledgement and adding a second warning on
failure. That still made the browser discard the operator's only draft before
the important operation finished. We instead narrowed the promise. A positive
`PROVIDER_INPUT_ACK` now means one of two precise outcomes:

- Codex accepted `turn/steer` for the active native turn; or
- an owned terminal thread resumed and `turn/start` returned a new native turn.

Everything before that is routing progress, not delivery. The browser holds the
draft while it waits. A rejection, a terminal race, or a timeout therefore
leaves the exact text available to retry instead of asking a person to remember
what disappeared.

The direct path stays equally narrow. A live message steers the app-server turn.
A terminal one atomically claims only the caller's own durable Codex invocation,
then calls the Codex tool directly. Neither route sends an outer `INPUT` frame
or calls `Agent.input()`, so the COAI model never gets a chance to rewrite a
native Work Room conversation.

That one acknowledgement distinction also made the UI calmer. The composer can
be honest about “sending” without inventing a local chat bubble; the native user
message appears only after Codex starts the turn, and the assistant response
arrives as a bounded native message. The Work Room can show the current
conversation, one current state, and optional real visual evidence without
trying to compensate for a missing delivery guarantee with more panels.

The regression tests now cover both halves: Host does not emit a false positive
ACK for a queue, and the native adapter emits one only after successful steering
or native turn start. This is the same rule as scoped Stop: intent, delivery,
and outcome are different states, and the browser should never render them as
one fact.
