# SMS is an Agent inbox, not an instruction channel

OpenOnion Messages began with a deceptively short request: let an Agent receive
the SMS that arrives on an Android phone. The important design choice was where
“receive” ends.

We made the phone and Agent runtime the cryptographic endpoints. Android seals
each new message to the Agent's existing public identity before upload;
`oo-api` stores routing metadata and ciphertext; ConnectOnion decrypts only
inside the project that owns the private identity. There is no second recovery
phrase and no server decryption mode.

That confidentiality boundary does not make SMS trustworthy. Carriers and
sender labels are not cryptographic identity, and a body can contain the same
prompt injection as an email or web page. The tool therefore returns every
message with `trusted: False`. Reading is not authorization. A later workflow
may extract a code or decide on an action, but that workflow must own its policy
and approval boundary explicitly.

The first version is deliberately prospective and narrow. Pairing is one-time,
short-lived, visible, and revocable. Existing messages are not bulk-uploaded.
Agents cannot send SMS. MMS, RCS, OTP parsing, and authentication orchestration
are separate product decisions rather than accidental side effects of inbox
access.

The result is three small responsibilities instead of one privileged service:
Android receives and encrypts, `oo-api` durably routes opaque bytes, and the
Agent runtime decrypts and labels the result honestly. That separation is the
feature.
