# Seven digits and the wrong suspect

`co outlook calendar list` worked on an empty calendar. Then someone created
their first events, ran it again, and got:

```
Error: Invalid input or Microsoft request failed; check the command arguments.
```

The arguments were fine and the request had succeeded. The time went into
checking the events that had just been made, because that is where the message
pointed.

Microsoft Graph writes event times with seven digits after the second:
`2026-09-28T06:00:00.0000000`. Python's `datetime.fromisoformat` accepts three
or six before 3.11, so on Python 3.10 — a version ConnectOnion supports — the
first real event made every calendar read raise `ValueError`. Our tests never
saw it: they fed times like `2026-09-28T06:00:00Z`, which no Graph response
contains, and CI's 3.10 job passed them happily.

Two things were wrong, and the second made the first expensive. The parser
now trims or pads the fraction to six digits before parsing, in one helper
used by every place the calendar reads a Graph time, and the tests feed it what
Graph actually sends. And the CLI's error handler no longer turns every
`ValueError` into "check the command arguments": it prints the error's own
words. A validation error we raise on purpose already says what to change; a
bug should say what it is, so that nobody goes looking for it in their own
input.
