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

The three branded senders are now verified and their sending DNS records are
installed. Incoming routing remains a separate acceptance step: the available
Cloudflare token could edit DNS but received 403 from Email Routing. Until
that permission and the catch-all route are checked, those domains must not be
sold as ready. The application tests and rendered desktop/mobile fixtures do
not substitute for that check, and no live email was sent for this work.

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
