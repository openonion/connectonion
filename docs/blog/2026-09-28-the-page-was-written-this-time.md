# The page was written this time

On Sunday night the Wiki investigated the owner's business partner, a person
with 157 emails over five months, and failed. It spent nearly two hours and
9.6 million tokens summarising his mail in fifteen pieces. The final step,
writing the page, then ran past its twenty-minute limit, and nothing was
saved.

The same night we tested the skills that write these pages with eleven cases.
Half of them failed, and all in the same way: the agent read everything it
needed and then went looking for an example to copy until it ran out of
steps. The model the Wiki uses in production had a version of the same
problem. It was given its material as 64-character fragments and spent a
dozen turns joining them before it read anything.

This preview carries both fixes. The skills say that the page and the
material are the whole input, and that the page should be written once and
then left alone. The evidence now goes straight into the prompt as text the
model can read. Run again on the partner, the investigation finished and
wrote a page with the terms the two of them had agreed, every dated
exchange, and one open question the mail itself raised. He says he signed,
but the copy on file has an empty signature line.

It still took three hours, because every one of the 157 emails was summarised
before a word of the page was written. The next change is to stop doing that
and let the agent search the mail for what each section needs.
