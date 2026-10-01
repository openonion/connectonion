# The page that kept being refused

The connectonion project page was 24,586 characters long when a new rule
arrived: a page may not end over 20,000 unless it is shrinking. The rule was
right. Pages had been doubling with every update, and every turn re-reads the
page it maintains.

The 1.9.0a6 acceptance run showed what happened next. The first sync sent
the page and its new messages to the model, which wrote a longer page, and
the review refused it for size: 79 thousand tokens, nothing saved. The second
sync sent the same page and the same four messages, 38,792 characters of
prompt, character for character. The model wrote a long page again, the
review refused it again, this time for a missing diagram, and another 180
thousand tokens went for nothing. Meanwhile maintenance reported the page as
"up to date", because as far as it could tell, it was.

Two things made the loop. The limit lived only in the reviewer. The model
writing the page was never told the page's size or the rule it would be judged
by, so it did what the page's shape asked and wrote everything down. And a
refusal left no trace. The messages stayed "pending", so the next run picked
them up exactly as before. Nothing had changed, so the outcome was the same.

Now the prompt states the page's current size and the limit before the turn
starts. A page near the limit is told to fold its oldest history into dated
one-line summaries first. A refusal is recorded against the messages it was
refused for, and the page waits until newer messages arrive instead of
retrying the same ones. The refused turn's copies of those messages are also
cleaned out of its task folder. Before, they stayed in it.

The same run found three smaller problems with how runs present themselves.
A run with nothing new now finishes as a success instead of an error. A sync
run off a terminal says each step as it starts. And stage timings are keyed
by stage rather than by stage plus progress count.
