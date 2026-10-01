# Names without links

Ody Zhou's page is one of the good ones in the owner's notebook: exact terms,
dated milestones, open threads that say who owes whom. It also mentions Ivan
Zhu, Harry Cao, James Guo, Ian and Emma, and every one of them has a page of
their own. None of them was a link. Across 381 people pages, two contained any
link at all. A notebook is meant to be a web, where reading one person leads to
the next. This one was a stack of separate files.

The skill asked for exactly one link: the Company field, to the organisation's
page. Nothing asked the model to link the people a page talks about, and the
model was never told which names the notebook had pages for. So it did what
the material showed and wrote names as text.

The obvious fix is to give the model the list of names and ask. That means
more context in every turn, and more chances to link "Harry" to the wrong
Harry. Instead the runner links after the model writes. Every page carries its
own title, so the notebook already knows which full names it has pages for.
After a page is written, the first mention of each of those names becomes a
link: exact full names only, never inside a Contact field or Sources, never
twice on a page.

The owner's notebook showed why "exact full names only" isn't the whole rule.
Ivan's page is titled "Ivan", because that is the display name his mail
carries, so "Ivan Zhu" in a sentence matched nothing. A first-name page is now
linked when it is the only page with that name and its address carries the
surname: `ivanxzhu@gmail.com` is Ivan Zhu. There are two pages titled "Harry",
so "Harry Cao" stays text. A wrong link is worse than no link.

`tidy` applies this to pages already written. On a copy of the owner's
notebook, Richard Lai's page now links Jiexuan Deng, Ody's links Ivan Zhu, and
the UNSW page links Jalaj Jain and Jiexuan Deng.
