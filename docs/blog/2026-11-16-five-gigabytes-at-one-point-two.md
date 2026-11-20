# Five gigabytes, stopped at one point two

Kim films on a laptop and edits on a mini PC in the office. The footage is
several gigabytes a day, and until now it went through a chat app, which
recompresses video, or through a cloud drive, which runs out. Both machines
already run a ConnectOnion agent, and both agents can already talk. They just
couldn't hand each other a file.

`co send` is that hand-off:

```bash
co send 0x1e85... ./C2350.MP4
co receive                       # on the mini PC
```

The interesting part is not the command. It's what the first real run found
that the tests had not.

## No new channel

Agents already open a sealed WebSocket to each other: `co call` and Remote
Browser use it, and it's encrypted end to end with keys both identities sign.
Files ride on it as four new frames. The sender offers the file's sha256 and
size, the receiver answers with how much of it it already holds, and the chunks
follow. A file is listed only once the bytes on disk hash to what was offered.

The relay is never used for the bytes. If the relay is the only way to reach
the receiver, `co send` stops and says so. Carrying gigabytes is not the relay's
job.

## Six megabytes a second

The first measurement was 6 MB/s, both ends on one machine. Profiling the
sender showed where the time went:

```text
   tottime  function
    10.344  {method 'compress' of 'zlib.Compress' objects}
     4.780  {built-in method _sodium.crypto_box_easy_afternm}
```

Half the time went to the WebSocket deflating frames that were already
ciphertext. Encrypted bytes don't compress, so every sealed socket had been
paying for compression and getting nothing back. Turning it off helps every
sealed connection, not only file transfers.

The other waste was signing. Every command on a sealed socket is signed, and a
chunk is a megabyte of base64. Signing and then verifying a megabyte cost more
than encrypting it. Now the signature covers the chunk's sha256 and the
receiver checks the bytes against it, which keeps the same guarantee for a few
dozen bytes of signing.

Between a laptop on Wi-Fi and the mini PC it now runs at the speed of the link:
raw TCP measured 11.4 MB/s and `co send` 8 to 14.

## What the real run found

The acceptance test was to stop a 5 GB send partway and send it again. It
stopped at 1.2 GB, and the second run began with
`sending 1.2 GB / 5.0 GB`. The sha256 matched on both machines.

But the first run had not stopped. The stop signal went to a background job
in a non-interactive shell, and those ignore it. So two senders were writing
into one staging file at once. The file only verified because the first sender
happened to give up early, after the receiver started answering it with offsets
it no longer expected.

Nothing in the tests sent the same file twice at the same time, because nobody
would do that on purpose. A resumed send does exactly that whenever the old
connection is half dead. Now each staging file has one writer: the newest offer
takes over, and the old sender is told `another send of this file took over`.

The same run found the second bug. Ctrl-C that lands inside a socket send comes
out as "connection closed", and the retry loop dutifully retried it and then
reported the receiver as unreachable. A task being cancelled is now never
retried: Ctrl-C prints how to continue and exits 130.

## What's next

`co send` needs the receiver to be reachable directly: same network, or a public
address. The mini PC sits behind the office router, so Kim can send from her
desk but not from home. Giving an agent behind NAT a public address is the next
piece of work (#3077).
