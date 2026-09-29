# Ten minutes and nothing to read

On 25 September the owner ran `co wiki init` on his own mail for the first time.
It was meant to be the start of a notebook about the people and projects in his
work. It ran for ten and a half minutes. The terminal filled with 15,498 lines,
most of them `listed gmail mail 2026-07-01 to 2026-07-08: 143`, one for every
seven-day window of every mailbox, and a `saving mail bodies` line every 25
messages. Somewhere above the last screen there was a summary.

When it finished he had 370 people pages, 138 organisation pages and 24 project
pages. Every one of them was an empty frame: a name, an address, a mail count and
"Unknown — not investigated yet" under every heading. The last line said
`Investigation: not started`. Above it were twelve questions, one per address
that might be his own, each with its own `co wiki init --mine <address>` to run.
The first page with anything written on it needed a second command,
`co wiki investigate me`, and nothing in front of him said so plainly.

His verdict was short: onboarding is not smooth. The first time someone uses
this it should be simple, clear, and give them something real.

## The page that was already there

The strange part is that init had already written something true about him. The
map fills the owner's own page with no model at all: how much mail he wrote and
received in the window, who he writes to most, which projects he has been coding
in and how many sessions each. It is the one page with value straight after the
map. The terminal never showed it and never said where it was. We had done the
work and then buried it under the progress log.

So the first change was to stop hiding it. When the map is done, init now prints
that page — its title, the facts on it, and its path — before anything else
happens. The progress log shrank to one line per stage: in a terminal each stage
rewrites itself in place, and in a pipe you get its finished line once. A 90-day
scan of one mailbox now prints five lines. Every step still goes to
`.state/init-progress.log`, for the day someone needs to know why a run was slow.

The twelve questions became one. The addresses that look like yours — you wrote
to them, they never replied — are listed on one line, followed by one command
that confirms the ones you keep: `co wiki init --mine a@x,b@y`. `--mine` now
takes commas.

## The command nobody had to discover

The bigger decision was the owner's: investigating "me" should start by itself.
Init stays a script that saves the raw material; when it finishes, it goes on to
write your own page, the same bounded first pass `investigate me --quick` ran.

A command that spends money on its own has to earn that. Before it starts, init
says which runner and model it will use, that it runs on your own Codex plan
rather than ConnectOnion credits, that it usually takes about ten minutes, and
that Ctrl-C stops it and keeps the map. `--no-investigate` skips it.

It also has to know when not to start. The first real failure of the old flow
was a signed-out Codex, discovered only when the model turn failed. Init now
checks the runner before the map begins, with no model: is it on PATH, is Codex
signed in. If not, it builds the map anyway and says once, at the end, what to
install or sign in to. It does not start when no mailbox gave an address of
yours, when your page is already written (a rerun should not pay twice), or when
nobody is at a terminal to read what it will spend; a script or `--json` has to
ask with `--investigate`.

One smaller thing fell out of the same run. The mailboxes init had just read were
left switched off for the daily round, so `co wiki start` listed them as
"unsubscribed", and the daily round never read mail at all. They are subscribed
now; `start` still asks before anything is read in the background.

## What we learned

We had measured init by what it built: how many pages, how complete the map,
how carefully it split a full week of mail. The person running it measured it
by what they could read when it stopped, and for ten minutes of waiting the
answer was nothing. The fix was mostly subtraction — fewer lines, fewer
questions, one fewer command — plus showing a page we had already written.

After a first run there is now one next step everywhere: `co wiki open` to read
your page, then `co wiki start` to keep it current. Right after your own page,
the same run writes the pages of the projects you worked on in the last two
weeks, from the messages you typed in their coding sessions: cost first, one
line per page, and it stops at the weekly budget. The people pages still start
empty; filling them a portion each day, most recent first, is the next stage of
#1943.
