---
title: An empty inbox was the wrong address
date: 2026-10-26
description: The mail API stays quiet about addresses you cannot read. The CLI was repeating that silence as "no mail".
---

Someone waiting on a reply ran `co email inbox --address someone@trustxmail.com`.
The address was not one this account owns. The command printed "Inbox: no emails
at someone@trustxmail.com" and exited 0.

That empty page is deliberate. Asking the received-mail API for an address the
account cannot read returns nothing, so a caller cannot probe which addresses
exist. The silence is the API refusing to answer. On 5 September that same
choice was written down: an error would have told a prober the address was
real. `co email default` already takes the other side of the trade for a
command that is allowed to know. It says the address is not this account's and
exits nonzero, because choosing a default is the account looking at its own
list.

The inbox filter had the list too. `co email addresses` reads
`/api/v1/email/addresses` with the same key. The CLI was treating the API's
refusal as the thing a person waiting on a reply most fears, which is that
nothing arrived.

The check runs only after a page comes back empty. Mail that did arrive,
including mail at an address this account can read because someone shared it,
is still that mail. A `can_read` grant with a genuinely empty mailbox stays
"no emails". A send-only grant does not count as a mailbox. When the address
is neither owned nor readable, the command names the addresses this account
does own and exits 1.

The regression was run against the unpatched handler first. It printed the
empty-inbox line and did not raise. After the change, the same test exits 1
and that line is gone. An owned address with an empty page still exits 0. No
message was sent, and no mailbox was opened on a real account for this fix.
The tests mock the address list, the share list, and the received page.
