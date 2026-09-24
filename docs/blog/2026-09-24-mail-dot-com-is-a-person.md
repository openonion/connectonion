# mail.com is a person

Two days ago the Wiki map learned to skip bulk senders. Newsletters and store
promotions come from a subdomain a company keeps apart from its people:
`mail.aitinkerers.org`, `e.domain.com.au`, `news.ato.gov.au`. A person writes
from the company domain itself. So an address whose domain starts with
`mail.`, `news.`, `e.` and a dozen similar prefixes, and which only ever wrote
to you, became a notice rather than a person page.

The rule was one label too generous. It matched `mail.` followed by anything,
and `mail.com` is followed by `com`. `mail.com` is not a company's sending
subdomain. It is a consumer mailbox provider, with millions of individual
people on it. A person there who had written to you and not yet heard back
lost their page, for the same reason a newsletter does.

The bug turned up while making a release screenshot, not in a user's notebook.
The synthetic owner in the capture had a second address at `mail.example`,
chosen to look ordinary, and it vanished from the list of possible own
addresses. Tracing why led to the regex.

A sending subdomain sits *under* a company's domain, so the rule now requires
a label after the prefix and another after that: `mail.company.com` qualifies
and `mail.com` does not. The regression test puts a `lee.chen@mail.com` who
wrote twice and never got a reply next to the newsletters, and checks that
Lee still gets a page.
