# One date without a timezone

`co rem init` promised a first page within minutes and quoted its estimate,
about 1.4 million tokens and eighteen minutes. Twenty seconds later it
stopped: "Your page was not written: Source contains an invalid timestamp."
No model had been called, and the owner's own page, the first thing a new user
is meant to see, was never attempted.

The timestamp belonged to one email among thousands, from a university
mailing address in July. Its Date header ended in `-0000`, which the email
standard reserves for "no timezone information". Python's parser honours
that by returning a time with no offset. co rem refuses a time with no offset,
on purpose: comparing a naive time with an aware one is how a message dated
in Sydney lands a day early in a window. The refusal was right. Where it
happened was not. One message's date ended the whole run.

We fixed it at both ends. The Gmail client now reads a `-0000` date as UTC,
which is what the standard says to assume, so new mail is saved with an
offset. Mail already saved in a notebook's archive stays as it is, so when an
investigation reads the archive, a message whose date cannot be read is
skipped and counted in the coverage. It no longer stops the run.

The same test found maintenance refusing every page it touched. A rule added
a day earlier said an investigated page may not keep "Unknown — not
investigated yet" in any section, which is fair for an investigation, whose
job is to fill them. It was also being applied to maintenance, whose job is
to add one fact from today's material. One sync spent 290k tokens and changed
nothing. The rule now applies where its own documentation said it should:
to a page's investigation.

Both failures had the same shape: a check that was right for one case, applied
more widely than that case. It was the scope that was wrong, not the checks.
