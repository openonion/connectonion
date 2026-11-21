# Unknown is not a sentence

*2026-11-15*

We shipped a table of organisations and, in the same release, a rule: a page
never prints "Unknown, not investigated yet" as if it were something we knew.
Then we opened the released build on a real notebook and seven rows said
exactly that, in the column headed "What they do".

The fix had been real. It caught the placeholder in the page's opening
sentence and in its list of connections, in English and in Chinese. What it
did not catch was a third route: a cached field called "Our relationship"
that held the placeholder half in each language, `Unknown — 尚未调查`. The
filter knew the English string and the Chinese string and not the mixture, so
it let it through, and the translator then tidied `Unknown` into `未知` and
produced a complete, confident sentence.

One rule applied in three places is three rules. Every summary the list and
the page print now goes through a single test of whether it is a real
summary, whichever field or translation carried it, and a cell with nothing
real in it shows a dash.

Writing the tests for that turned up something worse. A new test opened an
organisation whose kind was "company" and waited for a section that never
came. The page had not rendered at all: the breadcrumb translated the kind,
and for "company" that translation threw before anything mounted. No
organisation in the notebook we test on has that kind yet. The night's
enrichment is about to start filling it in, and every page it touched would
have gone blank.

Neither of these showed on the invented notebook the screenshots use. The
first needed data that had been through a translation cache; the second
needed a value nobody had written yet. We look at the real notebook after
every release now, and we looked at one more column than we meant to.
