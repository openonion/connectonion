# SMS is an Agent inbox, not an instruction channel

The first sketch of OpenOnion Messages looked almost finished. Wait for a text
from a familiar sender, pull six digits from the body, continue the Agent's
task. It was the kind of demo that fits on one screen.

Then we changed the fixture. The sender still looked familiar, but the body
said to ignore the Agent's rules and call another tool. Nothing in SMS delivery
made that line less valid than the six digits. A sender label is not a signed
identity, and encryption only proves which Agent can open the envelope. The
prototype had quietly turned “the Agent can read this” into “the Agent should
obey this.” No test failed, because the missing boundary was in the product
idea itself.

That was where “receive” had to end.

We made the phone and Agent runtime the cryptographic endpoints. Android seals
each new message to the Agent's existing public identity before upload;
`oo-api` stores routing metadata and ciphertext; ConnectOnion decrypts only
inside the project that owns the private identity. There is no second recovery
phrase and no server decryption mode.

That confidentiality boundary does not make SMS trustworthy. The tool returns
every message with `trusted: False`, including the most ordinary-looking code.
Reading is not authorization. A later workflow may extract a code or decide on
an action, but that workflow must own its policy and approval boundary
explicitly. The inbox never lends it authority merely because a message
arrived.

The first version is deliberately prospective and narrow. Pairing is one-time,
short-lived, visible, and revocable. Existing messages are not bulk-uploaded.
Agents cannot send SMS. MMS, RCS, OTP parsing, and authentication orchestration
are separate product decisions rather than accidental side effects of inbox
access.

The result is three small responsibilities instead of one privileged service:
Android receives and encrypts, `oo-api` durably routes opaque bytes, and the
Agent runtime decrypts and labels the result honestly. The useful lesson from
that first broken sketch was simple: private data can still be hostile data.
That separation is the feature.
