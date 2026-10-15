# 1.9.3b3: in the list this time

*2026-10-15*

Yesterday's preview put the sender's conversation into the recipient's Codex
as a thread of its own. A colleague tested it in a Codex they had been using
for a while, and the thread wasn't in the list. You could open it by its id,
but nobody types an id they were never shown.

Codex keeps its list in a small database. It reads new conversation files into
that database once, the first time it runs, and never again. Our earlier test
passed because the thread had already been opened by its id, which adds it to
the database. Now accept asks Codex to read the thread once, through Codex's
own interface, and it is in the list.

The same review caught a quieter problem. The receiving agent did the work and
reported back, but never told its person the thread existed. The last command
it runs now repeats the line.

```bash
python -m pip install --upgrade 'connectonion==1.9.3b3'
```

See the [release notes](../releases/1.9.3b3.md).
