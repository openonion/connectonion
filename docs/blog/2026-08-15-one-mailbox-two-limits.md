# One Mailbox, Two Limits

The two calls look interchangeable:

```python
get_emails(last=1000)
get_sent(last=1000)
```

They are not. Production accepts a thousand sent messages, while received mail
accepts 100 and answers HTTP 422 at 101. The SDK and CLI exposed both through
the same `last` idea without documenting that asymmetry, so the only way to
learn the received limit was to cross it.

The tempting repair is to clamp 1000 down to 100. That would make the request
green while making its meaning false: a reconciliation job would believe it
had asked for—and received—a thousand messages. Silent incompleteness is worse
than a loud limit.

ConnectOnion 1.6.7 therefore states the production contract at the client
boundary. `get_emails(last=...)` accepts 1 through 100 and rejects anything else
before it reads credentials or makes a request. `co email inbox --last` exposes
the same range as a usage constraint. The sent endpoint remains independent and
continues to accept 1000.

This does not pretend that a page of 100 is mailbox history. Complete
reconciliation still needs backend cursor pagination, and sender filtering
belongs on the server rather than after downloading a global inbox window. The
patch makes today's finite contract honest while leaving that larger API work
visible.
