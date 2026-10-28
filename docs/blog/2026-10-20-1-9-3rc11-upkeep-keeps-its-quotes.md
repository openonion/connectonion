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

## 27 October: keeping the words twice

Preserving evidence can make a page worse in a different way. A saved nightly
candidate and the current page differed by two extra lines, consistent with a
review that recorded two restorations: an almost repeated History event and an
old lead below `Uncertainties: Unknown`. That comparison does not establish the
exact promotion postimage or rule out a later edit. A second repeated obligation
was already in the candidate, so the restoration code could not explain it all.

An invented example isolated one deterministic cause. Nora's earlier quote was
“I will reply after Friday”; the new quote kept those words and put a full stop
inside the marks. The guard compared whole quoted strings, called the old quote
lost, and put the old sentence back. Asking the writer to distill again would
leave that guard unchanged. Removing the guard would again lose evidence.

The candidate repair instead recognizes literal words inside one longer quote
with the same immediately bound originals. It does not erase spaces or join
separate quotations; `able to pay` is not retained inside `unable to pay`.
Renumbered citations can name the same original, but an ID elsewhere in Sources
cannot lend its identity to a different quote. Truly missing introductory prose
returns to the introduction, retaining the new lead too.

The tests separate preservation from truth. A matching span does not prove that
its new surrounding claim is accurate, and it cannot fix a duplicate the writer
already supplied. The original review gate remains. This is an unreleased
follow-up to #2687, not a repair of the owner's saved notebook or proof of current
model usefulness. Native page and source-entailment acceptance remain separate.
