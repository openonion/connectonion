# The roadmap said 1.7.0

We were one preview away from stable 1.8.9 when someone opened the roadmap to
check what was left. It said the current milestone was 1.7.0. The project
instructions every coding agent reads before touching the repo said the
current candidate was 1.7.0a2 and stable was 1.6.4. Stable had been 1.8.8 for
weeks.

That was the funny one. The rest were not funny, because they were the kind a
reader copies. The same instructions told agents the default model was
`co/gemini-3.7-flash`; the code had moved to 3.8. They described a
`connectonion/listen/` package with a `mailbox.py` in it, and that directory
no longer exists: it became `connectonion/inbox/`, with Telegram, Discord and
WhatsApp beside Feishu. The browser page taught `--engine onion`, while
`co browser --help` lists `wtf`, `system` and `auto`. And two pages promised
that `co status` would suggest `co/llama` when your balance hit zero. It
suggests `co/gemma` and a local `ollama/<model>`. Someone out of credits reads
that tip at the exact moment they are deciding whether to give up.

Nothing had failed. The tests that guard our docs check that a model name
still answers, that every release has notes, that the checklist names real
files. Each of those held. None of them asks whether a sentence that says
"current" is still current, and a doc that is wrong about *when* passes every
check that is right about *what*.

So we did the audit the slow way: every claim checked against the code on
main, not against another doc, because two docs agreeing is how the `co/llama`
line spread from one page to a second. The tip in the docs is now the tip the
command prints, character for character. The roadmap is dated and says what
1.8.9 is (fixes, docs and doc tests; features already in PRs ship in the last
preview) and what waits for 1.9. The instructions no longer name a preview
number at all. They point at `VERSIONING.md`, which the release test already
keeps honest.

The lesson we took: a status line is a claim with a date on it, whether or not
anyone wrote the date down. Write the date, or point at the one file a test
keeps true. Anything else starts rotting the day it merges.
