# The side door had the old lock

Picture a user with two agents. One is their own, agent A, where they are the
admin. The other, agent B, belongs to someone else and is useful for asking
about the weather. The user asks B about the weather. Their client signs the
request, addressed to B, and sends it.

B keeps a copy. It posts that same signed request to A's `POST /input` and
adds a conversation history of its own: the "user" asking to email
`~/.ssh/id_rsa` to an outside address, and the "assistant" saying it has
done that. A checks the signature. The signature is real, because the user
really did sign it, so A runs the turn as the user, which on A means as an
admin, with a history the model takes to be the user's own. Then B sends the
request a second time and A runs it a second time.

We reproduced this with fakes and no network while auditing the hosting code.
What made it worth writing up is that none of the checks it needed were
missing. The WebSocket door already had every one of them. A CONNECT must name
the agent it is meant for, so a frame signed for B is refused by A. Each
signature can be used once, so a copy does no good. Every command on the
socket is signed along with its type and a nonce. These checks went in over
several releases, each after an attack like this one. The HTTP routes were
written before those releases and were never brought up to date. `/input`
called the plain signature check that predates all of them, and it read
`session`, `images` and `files` from beside the signature rather than from
inside it.

The audit found the same gap in three more places. A turn run by the
scheduler has no signer, so its session was stored with no owner, and
`GET /sessions` gave ownerless sessions to anyone who asked. A key generated a
moment earlier read a scheduled inbox digest from a host set to
`trust="strict"`. The WebSocket `ADMIN_*` frames were handled even on a
socket that had never sent CONNECT, and the action came from the frame's
unsigned `type` field, so an admin's signed BLOCK could be sent back with
`type` changed to UNBLOCK, or sent twice as PROMOTE to move a stranger up to
the whitelist. The HTTP body, which is read before any signature is checked,
was built with `body += chunk`. That cost grows with the square of the size,
and a 128 MB upload held the event loop for 23 seconds.

It would have been easy to write four new checks, and that would have left
the codebase with two versions of each one. We reused the existing checks
instead. `/input` now calls the same `authenticate_connect` that CONNECT
calls: signature first, then recipient, then the replay ledger, then trust
policy, in that order. It reads the session only from inside the signed
payload. `GET /sessions` now takes the signed headers that publisher routes
already use, which name the recipient and carry a one-use request id, and a
session with no owner is treated as belonging to the host, so only its admins
can read it. Admin frames go through `authenticated_command_payload`, the same
function every protocol-v2 command already passes through. The body reader
now collects chunks in a list and joins them once, and it stops at the same
256 MB limit the WebSocket already enforces, returning 413.

None of this required new rules. Each check already existed on one door and
was missing from another, and nobody noticed because each door looked secure
when examined by itself. The question that found these bugs was not whether a
route checks the signature. It was whether a route checks everything CONNECT
checks, and if it doesn't, why not.
