# The mini PC was asleep

`co send` went out yesterday, and the first thing Kim tried was the case it
does not cover. She was at home, the editing mini PC was in the office behind
the router, and she wanted to send a two-page PDF of cut notes:

```text
co send: 0x1e85d1… is not reachable directly from here
```

A direct send needs the receiver's Host to be online and reachable. For five
gigabytes of footage that is the right rule. For a PDF it is a wall.

## Small things wait

Now a file of up to 10 MB waits on the server when the receiver cannot be
reached, for 7 days:

```text
cut-notes.pdf  2.4 MB  sha256 9c1f0e7a2b44…  waiting for the receiver, encrypted to it, for 7 days
```

On Monday, `co receive` on the mini PC takes it, checks it, and deletes the
server's copy.

The server holds a NaCl box sealed to the receiver's key. The name and sha256
are sealed in a second box, so what the server knows is two addresses and a
size. The box also proves who sealed it. The server's word for who sent a
file is never what decides whether it lands. The key that made the box does.

## Same rule as a direct send

A waiting file lands only if it is from a contact, a whitelisted address or an
admin. That is the same bar a direct send has to clear. Anything else stays on
the server, and `co receive` says whose it is and when it will be deleted, so
adding the sender with `co trust add` and running `co receive` again is
enough.

## Why 10 MB

The server should not be where gigabytes sit. Notes, stills, a contract, a
config file: those are the things that need to get there while nobody is
looking. Footage still goes direct, and reaching an agent behind a router
directly is its own piece of work (#3077).
