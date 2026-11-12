# When a name is not enough

*2026-11-03*

Imagine two notebook pages titled Aster Vale, each with a different email.
Searching that name put one person's contact facts above the results under
“Best match.” Asking for pages related to that name went further: it showed
the first person's connections. The order of the files had become an answer
to a question about identity.

The command line already had the right contract: list the people with their
emails and show none. Bringing that rule into the reader exposed other places
where a name could quietly choose someone. Morning cards inferred a counterpart
from the first matching name; investigation selectors could follow the first
matching merged-page short name.

The first fix passed its tests, but independent AI review found a complication.
A page titled just Aster could still win over Aster Vale. Automatic links could
also discard duplicate full names, then infer that same name back onto a
first-name page. We added failing tests for those cases before fixing them.

The reader now offers candidates with visible identifying facts and waits for
a choice. A unique full name still works directly. Identity details keep their
original qualifiers, and labelled private facts stay hidden. Ambiguous inferred
links stay unlinked. None of this needs a new identity store: the safeguard is
to stop treating file order as evidence.

A follow-up browser check exposed another distinction. Searching Aster could
offer Asteron North and Asterley Reed as identity choices. Those pages contained
the search text, but neither recorded Aster as a name. The picker now compares
whole recorded names, first names and aliases, ignoring case. Six new regression
cases failed before that fix. Longer names still appear in the ordinary search
results; when only one identity matches, its best-match card returns. Finding
text and identifying a person need different matching rules.
