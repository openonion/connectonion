# The space that changed the quote

A source says “not able”; a notebook quotes “notable”. REM accepted the quote.
Its comparison removed all whitespace, so two different statements became the
same string. The reverse mistake passed too.

Removing spaces had a purpose: mail wraps lines, and copied text brings tabs,
reply markers and formatting. Requiring identical layout would reject valid
quotes. The repair keeps a single space between words while still folding case,
formatting and punctuation spacing. Han and kana text can still wrap between
characters; Korean word spaces stay significant.

The same checker validates session decisions. Fixing it alone would leave those
callers passing originals with their spaces already erased. They now pass the
retained text, both when saving a summary and when rebuilding its displayed page.

Before the production change, the regressions produced ten failures and seven
passing layout controls. They cover joined and split English and Korean words,
summary creation, and old saved summaries. This is a literal comparison fix;
speaker attribution and ambiguous fragments inside larger words still need
source judgment. It does not establish that a quotation supports its surrounding
claim.
