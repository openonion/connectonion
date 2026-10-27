# Nine of nine

The first init that translated its own pages wrote nine pages and cached
eight translations. The ninth was refused because the model had changed one
of the page's source ids. A rerun passed, so the failure was chance, and
chance is not good enough for the last step of somebody's first run.

Two changes fix it. The `## Sources` section, the one that is nothing but ids
and dates, is no longer sent to the model at all. It is copied back byte for
byte after the translated prose, so there is nothing there for the model to
get wrong. And when the check before caching fails, the model gets one repair
turn with the exact difference, such as "missing [12] (1 time)", instead of
the whole page being thrown away. On the same trial notebook all nine pages
were then cached, one of them after a repair.

We also read translated pages next to their originals. Dates, citations,
email addresses and quotes came through intact, and the Chinese read
naturally. Two things did not. "$50,000 per year" became "每年 50,000
美元": the page never said US dollars, and the model had decided it on its
own. A project called `handoff` was sometimes translated as 交接, which hides
the name of the thing. The prompt now says to keep every amount and currency
symbol exactly as written, and to keep names as written, including lowercase
project names. It passes the page's title and link texts as an explicit list
of names to keep. Both came out right on the next run.

Then a full notebook: 297 written pages at 16 workers. 296 were cached, with
10 repairs. The one failure was a check that was too strict: a line
beginning "#1037" (an issue number) counted as a Markdown heading. It now
needs a space after the hashes. The run took 66 minutes and 26.9M input
tokens. Init's estimate had said 12 minutes, because it assumed 35 seconds a
page. That is how long one translation takes alone. With 16 turns running at
once, each takes about three minutes, since they share the model's
throughput. The default is now 200 seconds and 90k input per page, which
puts the same notebook at about an hour. After a notebook's first run, its
own measured medians replace those defaults.
