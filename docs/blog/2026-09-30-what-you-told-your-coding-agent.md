# What you told your coding agent

The owner's first run of the notebook made 24 project pages, and every one of
them was a frame: fifteen headings, each saying `Unknown — not investigated
yet`. The information to fill them was already on the laptop. Every day he
explains his projects to Codex and Claude Code: what he is building, what just
broke, what he decided and why. Those sessions are saved locally. Nobody had
read them for the pages.

So the first plan was simple: read the sessions, write the pages. Then we
counted. On his machine, 1,567 session files had changed in the last 180 days,
4.4 GB in total. Almost all of it is not him. It is tool output, test logs, the
assistant's replies, and the text the clients inject into the user's turn,
such as environment blocks, skill bodies and subagent prompts. A model given
all of that writes a page about test counts and commit hashes. We had already
seen that happen.

What he actually typed was 1,359 messages. 614 of them were typed in folders
that are not projects: the `~/projects` workspace that holds six repositories,
and temporary directories. The other 745 messages came to 203 KB across 43
project folders. The busiest folder had 38.7 KB, the median under 1 KB. That
changed the design. The material is small enough to hand the model whole, so
it does not need a search step or chunk summaries, and a page is one call.

That gives two steps. The first is a script with no model. It walks the
session files with the same parser `sync` uses, keeps only what he typed, files
each message under the project page whose folder it was typed in, and saves it
in the notebook's private `.state/`. Anything shaped like a key is replaced
before it is written. The second step is one model call per page, given the
page and those messages and nothing else. It works through the most recently
active projects first, because a page about last week's work is the useful one.

The first real run failed in one second. The prompt started with the new
skill's name as a slash command, and `co ai` could not find a skill by that
name, so it refused. The fix was to start the prompt with the notebook's task
tag instead. That turned out to matter for a second reason. The run's own
prompt is saved in a session file too, and the tag is what makes the next
extraction skip it. Without it, the notebook would have read its own
instructions back as something the owner said.

The second run took 65 seconds and the page passed review. It had all fifteen
sections, 27 citations each pointing at one of his messages, and five lines
left as `Unknown` where his messages did not say.

One thing did not match. We had stated the cost as the size of the prompt,
about 12,000 tokens. The runner used 86,710 input tokens, most of them cached.
It is an agent, and it sends its context again on every turn. The cost line
now says both numbers: what one prompt carries, and that the bill is several
times that.

The lesson is the one the notebook keeps teaching. Measure before you design.
Counting 745 messages told us one call per page was enough. Running the command
once told us the cost line was off by a factor of seven.
