# The Third Argument Was Already Taken

`co outlook reply` could not attach a file. `co outlook send` could. The fix
looked like an afternoon's work: reuse the validation, the 3MB ceiling, and the
MIME sniffing that `send()` already had, then hang the result off Graph's reply
action so the message stays inside its original thread.

The signature wrote itself, because `send()` was sitting right there:

```python
def send(self, to, subject, body, cc=None, bcc=None, attachments=None, send_at=None)
def reply(self, email_id, body, attachments=None, send_at=None)
```

Two methods, same tail: `attachments`, then `send_at`. It reads as symmetry.
Eighty-nine tests passed, including every attachment case I could think of — a
missing file, an oversize file, a file outside the project, a Graph rejection
that must not be reported as a sent reply.

Then a reviewer asked what happens to the code that was already there.

`send()` was born with `attachments` in that slot. `reply()` was not. Its third
positional argument had been `send_at` since the day it shipped:

```python
outlook.reply(email_id, "See you then", "2026-07-06T15:30:00Z")
```

No test in the repo caught this, because every test in the repo passes
`send_at=` by keyword. Callers outside the repo have no such habit. After my
change, that line handed a timestamp to `attachments` — and `attachments` gets
iterated:

```
ValueError: Attachment not found: 2
```

`"2026-07-06T15:30:00Z"` is not a list holding one path. It is a sequence of
twenty characters, and the first one is `2`. The CLI version of the same
mistake is better still: the old `handle_outlook_reply(id, message, "+30m")`
now complains about a missing file named `+`. The scheduled reply never leaves,
and the error blames a file the user never typed.

I had been careful about the parts that looked dangerous — a file swapped
between validation and read, an encode that must finish before the POST so a
rejected attachment cannot leave a reply already sent and unattached. The bug
was in the part that looked like tidiness.

The repair is one `*` and a swap:

```python
def reply(self, email_id, body, send_at=None, *, attachments=None)
```

`send_at` keeps the position it has always had. `attachments` moves behind the
star, where argument order cannot reach it — not now, and not the next time
someone adds a parameter and wants the two signatures to line up. Two
regression tests pin the legacy positional call, and a third asserts the
parameter list itself, so the contract now breaks in CI instead of quietly in
somebody's mailbox.

The lesson isn't "be careful when adding parameters." It's that symmetry
between two functions was something I wanted, while positional order was a
promise the older function had already made. When those two disagree, the
promise wins.
