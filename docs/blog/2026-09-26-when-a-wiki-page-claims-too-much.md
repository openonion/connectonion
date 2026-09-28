# When a Wiki page claims too much

The project page looked finished. It had the expected sections, citations, and
an investigation timestamp. Then I reached the last line. It said a source had
been investigated even though the run had not searched that source. Nothing in
the prose needed to be fabricated for the page to mislead a reader; its own
status label supplied a false sense of coverage.

I traced the label back to the collector. It had reported both searched and
unsearched source states, but the page writer treated every reported state as
a completed search. The fix was small: only a successful search can enter the
"Investigated" list. An unavailable or unsearched source stays visible as a
limit, where it can prompt a later pass instead of quietly becoming apparent
evidence.

That discovery changed how I reviewed the rest of the run. A page can pass its
shape checks and still be wrong about what it knows. I compared a shorter
investigation instruction against retained evidence. It finished faster, but
missed relevant implementation files. I kept the slower instruction. The
benchmark now asks whether the claims are supported and the important sources
were read before it looks at time or tokens.

The lesson is about the boundary of an investigation. A citation, a tidy page,
or a quick finish does not establish that the work was done. The page should
say what was actually searched, and our acceptance check must inspect the
original evidence before deciding it is ready to trust.
