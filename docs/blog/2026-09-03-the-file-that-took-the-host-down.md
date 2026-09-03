# The file that took the host down

At 03:11 UTC the Melbourne rental host stopped answering anyone. Not crashed:
`systemctl` said `active/running`, the relay heartbeat was on time, `/health`
returned 200. Every signed request — `co call`, the RemoteAgent sessions the
CRM tooling uses, the Lark gateway — came back with the same line:

```text
✗ CONNECT auth error: misconfigured: replay protection unavailable
```

217 times, over 2h44m, until someone SSH'd in and restarted the service.

## What the file was for

`.co/replay.sqlite3` is the one-use signature ledger. A CONNECT is signed and
carries a timestamp; for five minutes the same bytes verify again, so the host
writes down the hash of every signature it has accepted and refuses a second
presentation. 1.7 kept that ledger in a dict. #805 moved it into SQLite so
that `create_app()` served with `uvicorn --workers 4` would share one ledger
across processes instead of accepting a captured frame once per worker.

The store creates its table once, in the constructor. Every later claim opens
a fresh connection to the path. So when a deploy's `rsync --delete` removed
the file — the helper's protect list did not name it — and then the helper
died on an unrelated missing `pg` module before it reached the restart step,
the next claim let SQLite quietly create an empty database, `DELETE FROM
used_signatures` raised "no such table", and the store did what it was
designed to do with any storage error: fail closed. Forever, or until a
restart. Two earlier deploys that night had deleted the same file; their
helpers restarted the service, so nobody noticed.

## What the file was not for

Two facts made the ledger's job smaller than it looked.

`host()` runs one uvicorn worker. It hands uvicorn an app object, and uvicorn
cannot fork an object; `usable_uvicorn_options` prints a line saying so and
runs one. Every `co deploy` host is that host. The cross-process ledger was
protecting a race those hosts cannot have, and paying for it with a shared
mutable file that a deploy script, a tmp-cleaner or an operator's `rm` could
take away.

The other fact shipped the day before. 1.8.0 seals direct sockets: one-time
X25519 keys signed by both identities, a NaCl box, a counter per direction.
Inside that seal a captured CONNECT cannot be presented by anyone who did not
complete the handshake, because they cannot produce a frame that opens. The
ledger has nothing left to catch there. It was still being consulted on every
sealed CONNECT, and its file was still the thing a deploy could delete.

## What 1.8.1 does

The relay path gets the same seal. This was smaller than it sounds: the oo-api
proxy reads `to` from the first frame to find the agent and forwards every
later frame verbatim with a `session_id` stapled on, and `SEAL` carries `to`.
The client offers `SEAL` on the relay socket exactly as on a direct one; the
host's relay session goes through the same `host_seal_or_pass` the ASGI
adapter uses. A relayed session is now ciphertext to the relay — prompts,
tool calls, outputs, files. The relay's own `PING` and its "Agent not
connected" still arrive in the clear and are passed up as what they are:
frames that hold no key and carry nothing a peer said.

One binding had to be added before the ledger could go. Inside a seal the
CONNECT — and an ONBOARD_SUBMIT — must be signed by the identity that signed
the SEAL. Without that, a stranger could open a seal of their own and feed a
CONNECT captured from someone else into it: the exact replay the ledger
existed to stop, now inside a channel the stranger controls. With the
binding, the host does not consult the ledger on a sealed socket at all.

For the unsealed 1.7 client the ledger stays, in memory, because a `co host`
process is one process. `.co/replay.sqlite3` is written only by a
`create_app()` deployment, and if that file is removed under a running host
the store puts its schema back on the next claim instead of refusing everyone.
Whoever could delete it already had host access; refusing every caller until
a restart protected nobody.

## Compatibility

A 1.8.1 client against a 1.8.0 host through the relay: the host answers the
SEAL with `unknown message type: 'SEAL'` and has consumed that socket's first
frame, so the client closes it and opens a fresh bare relay socket — TLS to the
relay, every client's footing before today. A 1.8.0 client against a 1.8.1
host opens with CONNECT and is held to the in-memory ledger as before. Nothing
falls back to plaintext on a *direct* public socket; that rule is unchanged.

## What was measured

The reproduction is one line: start a host, `rm .co/replay.sqlite3`, make one
`co call`. On 1.8.0 the call fails and keeps failing; the regression test does
that to the SQLite store and expects the second claim to succeed and the third
— the same signature again — to be refused. The relay tests drive
`relay._run_session` with the frames a real proxy produces, `session_id` and
all, and open the host's replies with the client's channel. The binding test
seals as one identity and sends a CONNECT signed by another, and was run
against the unpatched tree first: it passed the stranger through.
