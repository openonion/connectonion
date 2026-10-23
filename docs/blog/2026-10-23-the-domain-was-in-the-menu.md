---
tags: [Email, API Design, Testing]
---

# The domain was in the menu

The owner asked whether one account could hold several email addresses on
different domains. There was code for that, they remembered. The natural next
step seemed to be finding the command and showing how to use it.

The cloud API returned four domain choices. Its address table could hold more
than one mailbox for the same account. The command line could list them and
send from one explicitly. What it could not do was set up another alias on a
chosen domain. That missing entrance explained why the feature was hard to
find, but it did not explain whether the mailboxes worked.

Checking the sending provider changed the task. Of those four advertised
domains, only mail.openonion.ai was verified. The three branded domains had
never been registered there. Two also had no incoming MX records. A successful
address purchase would have proved ownership of a database row; it would not
have established a working mailbox.

There was another disconnect inside the application. Choosing a default
address changed the flag in the address table. A later send without an
explicit sender still read the older account settings. The CLI could show one
default while the email left as another. The independent review caught that
path by following the flag all the way to the provider request.

The repair connects these existing parts. Domain choices and prices come from
the cloud, and setup adds another address while preserving the account's
mailboxes. An owned default takes priority when a send leaves its sender
unspecified. An operator can restrict the domains offered for new purchases
until the deployment is ready to serve them. Maintaining a second fixed list
in the CLI would have recreated the original disagreement.

Closing a domain to new purchases exposed another edge in repeat setup. The
CLI checked the current domain menu before looking at the account's owned
addresses, so a person with a valid mailbox could be told that its domain was
unknown. Checking ownership first lets setup recognize that existing address
without another purchase. New claims still have to pass the readiness gate.

The three branded senders are now verified and their sending DNS records are
installed. The first routing inspection used the production DNS token, which
received 403. A later check of the shell's dedicated email token could read
rules and Workers, but enabling a zone still returned 403: that operation needs
Zone Settings Write. Inspecting the existing routes mattered too:
trustxmail.com was already serving a separate verification-code worker. The
owner chose to move all of that domain's mail to Agent Mail. Its original rule
was backed up, the catch-all was changed, and a real test reached the mail store.
It now joins mail.openonion.ai in the enabled choices. steadmail.com and
oakinbox.com still need their routing enabled before they can be offered.

A real self-test subsequently reached the owner's existing primary inbox through
the deployed mail Worker and signed backend webhook. It was sent with the
service's provider account because the owner's CLI send request hit its monthly
100-message quota. That verifies the primary incoming path; the separate trustxmail.com test
verifies that domain's path into the mail store. Neither establishes a successful
send through the quota-limited account or delivery to the two unenabled domains.

The follow-up question was simpler than the original setup request: would
these different names still be one inbox? A test account acquired five
addresses across the four hosted domains, including the same name on two
domains and two names on one domain. Its received-mail query returned all
five destinations. Changing the default sender did not remove any of them;
filtering by one address narrowed the list, while another account's message
stayed outside it. That was exercised against real PostgreSQL, so the check
covered the address lookup and inbox query together. It still did not prove
that an outside sender could reach an unconfigured domain.

The useful boundary turned out to be the purchase. A domain belongs in the
public choice list when the deployment can provide the mailbox behind it.
Being reserved, registered with a provider, or present in a table answers
three smaller questions. None alone answers the one the user asked.
