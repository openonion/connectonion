# 1.9.3rc11: upkeep keeps its quotes

*2026-10-20*

rc9 shipped two REM bugs, and this candidate fixes both.

Daily upkeep could rewrite a page and lose what it had. In one replay, a page
with twelve quotes came back with none. Upkeep now checks a rewrite against the
page it replaces, the way enrich and muse already did.

The pronoun repair guessed. It turned a sentence about the subject's manager
into one about the owner's. It now only rewrites he, his and she, and never the
form the page uses for its own subject.

How each one was found is in
[The repair that guessed](2026-10-20-the-repair-that-guessed.md). The deepen
picker changes are in
[An empty page is not a reason](2026-10-20-an-empty-page-is-not-a-reason.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc11'
```
