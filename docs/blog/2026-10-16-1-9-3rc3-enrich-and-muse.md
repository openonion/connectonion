# 1.9.3rc3: asking a better question

*2026-10-16*

A page `co rem investigate` writes is as good as what its gather found. On a
real project page, the gather had found the repository's README, its recent
commits and the owner's typed requests. It had not found the mail about the
service's access, the pull requests the commits linked to, or the deployment
run that settled whether the last change was live. Nothing on the page was
wrong. It was thin, and it did not know where else to look.

This candidate adds two commands for one written page.

## enrich: what else exists

`co rem enrich PAGE` hands the model the page, its cited originals, and a
ledger of every source the saved archive holds about the subject, with the
ones the page does not cite yet listed first. Its job is discovery: open the
links, read the attachments, find the start of a `Re:` thread, follow a name.
It ends with a lead list, followed, open or blocked, so the next run starts
where this one stopped.

On that project page, enrich went from 5,164 to 9,032 characters and from 10
cited sources to 20. It found that the code's default model and the README
disagreed, that an issue thought fixed was only half fixed, and that the
deployment had in fact succeeded. Every quote the page had before was still
there.

## muse: what it means

Enrich adds facts. The prototype's lesson was that more facts do not make a
better page; a precise question does. `co rem muse PAGE` runs as one
conversation of seven turns in the same thread. The first asks at least twenty
questions of the page and its originals and picks five. Each of the next five
studies one, and edits the page only when the answer is an insight: something
no single message says, that needed two sources, that changes what the owner
believes or does. "No insight" is a normal answer. The last turn looks back
and brings the lead in line with what changed.

The skill took nine rounds on real pages. Early rounds wrote "Inference: … does
not establish …" into the Insight section; that is now named as never an
insight. Others replaced a quote with a better one and lost the original; the
runner now puts the page back if any quote or cited source from the start of
the run is missing.

On the enriched page, muse made it shorter, 9,032 to 8,514 characters, with
the same six quotes and one more source: the last turn folded what its
insights superseded. It cost 16M input tokens, almost all cached, because
seven turns re-send a growing context. Thinking slowly is not cheap, which is
why it runs only when you ask.
