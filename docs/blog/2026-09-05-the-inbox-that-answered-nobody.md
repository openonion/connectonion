# The inbox that answered nobody

A job application went out on Tuesday with the wrong email address on it. That
part is an ordinary mistake. What made it worth writing down is what happened
next: **nothing**.

OpenAI's recruiting system replied within the hour. The mail was accepted,
routed, and stored in `email_received` exactly as designed. No bounce, because
nothing bounced — the address resolved, the message was delivered, the row is
still there. It simply belonged to a second account of the same person's, and
`co email inbox` on the machine that sent the application showed an empty
result where the answer was.

The only symptom was silence, and silence is what you expect while you wait.

## The mail was never lost

The address was `aaron@mail.openonion.ai`. The account doing the work owns
`aaron.xie@mail.openonion.ai` — a rename from a month earlier that a document
had not caught up with. Two accounts, one person, one of them not the one
holding the mailbox.

The obvious fix was already in the product. `co email share --can read` grants
another account read access to one of your addresses, and #1137 shipped both
the command and the `email_grants` table with a `can_read` column.

We ran it. The row was written. The output said so. Nothing changed.

```
email_grants row       ✓ can_send=t  can_read=t  revoked_at=NULL
co email inbox         ✗ the mail is still not there
```

## can_read had never been read

`account_inbox_addresses()` builds the filter both read paths share. Its
docstring lists four things that can route mail to one account — the derived
`0x…` address, the tier's alias, a purchased custom name, and the rows in
`email_addresses` — and it was scrupulous about all four, because an earlier
bug had lost 173 messages by omitting one of them.

It never consulted `email_grants`. Grants were checked on the **send** path
only, through `may_use_email_address()`. So `--can read` wrote a durable,
correct-looking row into a table nothing queried, and reported success.

A column that exists, a flag that writes, a command that returns zero, and no
effect anywhere. From the outside this is indistinguishable from a working
feature — which is the whole problem with it.

## What we changed

`account_inbox_addresses()` gained a fifth source: addresses granted with
`can_read` and not revoked. Two more things came along with it, because the
same investigation kept running into them:

- **Every received message now carries `to`.** An account reading two mailboxes
  used to get one merged list with no way to tell which address anything
  arrived at — ambiguous precisely when it matters.
- **`GET /received?address=` narrows to one mailbox.** The filter *intersects*
  with the readable set and can never widen it, so asking for an address you
  cannot read returns an empty page rather than an error. An error would tell a
  prober which addresses exist.

The default sender became settable too (`POST /addresses/default`), restricted
to owned addresses. A granted address can be revoked by its owner at any
moment, and a default that vanishes underneath you is worse than no default.

`delete_address_mail()` stayed gated on `owns_email_address()`, not on the read
set, so `can_read` cannot escalate into deleting somebody else's mail.

## The client fails closed

`get_emails(address=...)` refuses a backend that ignored the parameter instead
of quietly returning everything. An older deployment answers an unknown query
string by handing back the whole mailbox, and "I asked for one address and got
all of them" is the exact failure the filter exists to prevent. The `offset`
parameter already had this guard; the new one copies it.

## What it cost to find

Five tests, each checked against the unpatched code first to prove they were
capable of failing. But the measurement that actually mattered came from
outside the test suite: sending a real message to the address and watching it
not arrive, then finding it sitting in the database.

The lesson we keep relearning is not "write more tests." It is that a write
returning success proves a write returned success. `INSERT 0 1` was true, and
the feature did nothing. The only check with any force was opening the inbox
afterwards and seeing the message that had been invisible for a day.
