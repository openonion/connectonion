# A Page Should Not Become a Wall

The two calls look interchangeable:

```python
get_emails(last=1000)
get_sent(last=1000)
```

They used to behave differently. Production accepted a thousand sent messages,
while received mail stopped at 100 and answered HTTP 422 at 101. The SDK and
CLI exposed both through the same `last` idea, so the only way to learn the
received limit was to cross it.

The tempting repair is to clamp 1000 down to 100. That would make the request
green while making its meaning false: a reconciliation job would believe it
had asked for—and received—a thousand messages. Silent incompleteness is worse
than a loud limit.

The first repair made the hidden limit explicit at the client boundary. That
was honest, but it preserved the wrong product behaviour: users still could not
reconcile an inbox larger than one hundred messages. A page boundary had become
a mailbox boundary.

The final repair aligns received and sent page sizes at 1000 and adds an offset
to every received-mail page. `get_emails(last=1000, offset=2000)` and `co email
inbox -n 1000 --offset 2000` now address the third page of an inbox. The backend
orders equal timestamps by message id as well, so rows do not swap positions
inside a page merely because their timestamps match.

A service still needs a finite page size to protect itself. The important
difference is that the boundary is now traversable. Callers can continue until
a page is empty instead of mistaking the newest slice for complete history.
