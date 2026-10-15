# 1.9.3b5: pages you can trust on the first run

*2026-10-15*

We read the first notebook `co rem` wrote for its owner, claim by claim. Most
of it was right, which made the wrong parts worse: 8 of 89 quotes were not in
their source, one person's page carried a stranger's mobile, and a student's
page named the university as their employer. A wrong phone number is worse
than none, because you call it.

At the same time, review was losing good pages. It had two answers, accept or
refuse, and a page with twenty sound sentences and one it could not find was
refused whole. On one trial run that single kind of refusal cost 10 of 28
pages and 29M input tokens.

So 1.9.3b5 checks more and refuses less. Quotes must be word for word in a
source their line cites. Every page about a person, an organisation or a
project is audited. A contact fact stays only when the person's own mail shows
it. When review finds a fault, the writer gets two turns to repair it, told
exactly what failed. What is still refuted after that goes with its sentence,
and the rest of the page is kept.

The reader changed too. `co rem open` now starts a live reader on your own
computer, and a page can be read in your language: the menu offers the
languages you write in first, detected from your own mail and sessions.

```bash
python -m pip install --upgrade 'connectonion==1.9.3b5'
```

See the [release notes](../releases/1.9.3b5.md).
