# A string of nothing but the letter a

The report arrived as a mystery about characters. A LinkedIn article body was
being handed to a fill script the documented way — `"$(cat args.json)"` — and
the browser refused it:

```
$ co browser -t t run_page_script echo.js "$(cat fill.json)"
unparseable request: browser argv contains an invalid value
exit 2
```

An invalid value. So you go looking for the invalid character. A smart quote,
a stray control byte from the editor, some mangled UTF-8 in the HTML. A
4,200-character article had been fine the week before; a 24,000-character one
was not. Something in the longer article, then. Something in *those* extra
twenty thousand characters.

The test that ended the search was a 73 KiB string of the letter `a`.

It was refused too.

## Two refusals wearing one sentence

Here is the line, in `network/oip/framing.py`:

```python
if b"\x00" in encoded or len(encoded) > 64 * 1024:
    raise ProtocolError("browser argv contains an invalid value")
```

Read it as a sentence and it is fine. Read it as two sentences and it is not,
because it *is* two sentences. A NUL byte in an argv entry is a malformed
value — the protocol cannot carry it, and no length would make it acceptable.
A 73 KiB entry is a perfectly well-formed value the protocol has decided not
to carry. One is about the bytes. The other is about how many of them there
are. They share nothing except the `raise` they were folded into.

And the fold is not symmetric in cost. A caller told their value is invalid
will inspect the value. That is the only reasonable thing to do with that
sentence, and it is exactly the wrong thing to do, and there is nothing in the
message, `co browser help`, or the docs that says so. The number 65536 appeared
nowhere the reporter could reach it.

## The check six lines down already knew better

What makes this worth writing up is that the fix was sitting immediately
below, in the same `if` block:

```python
if encoded_size > 128 * 1024:
    raise ProtocolError("browser argv exceeds 128 KiB")
```

That one names its limit. Someone writing the aggregate check thought about
the person who would hit it; someone writing the per-entry check — probably
the same person, minutes earlier — reached for "invalid" and moved on. The
inconsistency is four lines apart and survived every review since, because
nothing about the code looks wrong. It only looks wrong from the outside, at
the moment you are holding a string of the letter `a` and being told it
contains something invalid.

So the messages now say what they found:

```
browser argv entry 2 is 73342 bytes; the per-entry limit is 65536 bytes
browser argv entry 1 contains a NUL byte
browser argv is 196605 bytes across 3 entries; the total limit is 131072 bytes
```

The entry index is in there because a command carries up to 128 entries, and
"one of them is too big" is not an answer when the payload was assembled from
several. Both limits are constants now rather than literals, so the numbers in
the message and the numbers in the check cannot drift apart.

## What did not change, and why that is the honest half

The caps are exactly where they were. The 73 KiB payload that started this is
still refused. It is now refused in a way that tells you to stop reading your
string and go find another way to pass it — which is a smaller thing than
fixing the workflow, and it is the part that was unambiguously broken.

Raising a protocol limit is a different decision, made by people who know what
else is sized against it. The reporter proposed the better answer in the same
breath: `run_page_script` could take `--args-file <path>` and read it the way
the daemon already reads the script from disk, so argv carries a path and the
payload never passes through the frame at all. That is a feature, and features
get discussed before they get written.

What the diagnostic fix buys in the meantime is the hour that went into
looking for a bad character. The next person gets two numbers and a decision,
instead of a word that sent the last one the wrong way.
