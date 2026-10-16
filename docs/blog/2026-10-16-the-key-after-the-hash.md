# The key after the #

*2026-10-16*

The launch film for handoff says "end-to-end encrypted". The README said, further down,
that it wasn't yet. Both were true, and only one of them was on screen.

Our backend held each handoff as a JSON row with the report, every message the
sender typed, the AI's replies, and the code that let anyone holding it pick the
handoff up. Readable by us, by a database backup, by whoever got into either.

The first handoff can't be end-to-end. The recipient has no agent yet when the mail
arrives, so there's no public key to encrypt to. Aaron put it plainly: there's no
end-to-end encryption at the start, but once the handshake is done, both sides have
keypairs, and from then on there is.

So the first message needs a key that travels with the person and not with us. A
URL has exactly one part that a browser never sends to a server: the fragment after
`#`. The sender's co now seals the handoff with a fresh AES-256-GCM key and puts the
key there: `o.openonion.ai/h/<id>#k=…`. The page fetches ciphertext and decrypts it
in the browser. The agent the person pastes the line into runs `co handoff accept`
with the same link and decrypts on its own machine. What we store is a blob, the
sender's name and which agent wrote the session. The prompt we serve to agents
names no title and no code. It just says to accept with the whole link.

After acceptance each side knows the other's address. That address is an Ed25519
public key, so the same key gives an X25519 box. Questions, answers and results now
cross the backend as `{"subject": "[co handoff]", "sealed": "…"}`. A box also proves
who sealed it, so a message re-posted under another agent's name doesn't open.

Then we measured what was actually stored rather than what we meant to store. Two
test identities ran a real handoff: send, accept by link, a question, an answer, a
result with a patch. We read every row back with their tokens and searched each one
for the handoff's words, the code and the key. We found none.

What this doesn't cover, we say in the docs. The note to the person is ordinary mail,
and it carries the link. Sent from your own Gmail, the key never touches us. Sent from
the agent mailbox, it passes through our mail service. The preview now says that too.
