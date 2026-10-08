---
description: co rem 1.9.1b1 keeps a paid-for page when only one citation is wrong, draws decisions and principles from the first run, and lists a page's documents.
tags: [REM, Memory, Reliability]
---

# One citation is not a page

The 1.9.1a2 first run wrote every one of 84 people. It lost six project pages,
and when we opened them, each was missing exactly one thing: a single citation
that could not be traced, or a source mentioned only inside a diagram.

That is a bad trade. A project page is minutes of reading and thousands of
tokens, and the review threw all of it away for one footnote. Person pages
stopped doing that months ago: an untraceable citation removes the lines that
rest on it and nothing else. Project pages kept the stricter rule so the model
could repair the whole page itself, and after two repairs the model had still
not fixed that one footnote.

1.9.1b1 lets the repairs run, then applies the person-page rule as a last
resort. The page keeps everything it can prove.

The same beta closes the loop the owner asked for this morning. After the
first run writes people, projects and organisations, it reads them once more
and asks a different question: what was settled here, and why? Those become
decisions; what keeps recurring across decisions becomes a principle. And
documents stop hiding behind footnotes: a page lists the PDFs it cites, one
click from the file.
