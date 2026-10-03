# People, recent correspondents first, and the four-run day (#1943, stage 3)

Since #1942, investigating a person no longer digests all of their mail: our
code gathers it, writes it to evidence files with an index, and one turn
searches those files for what the page needs (#1850). This stage decides
**who** is investigated next, **over which window**, and **when** the daily
round does it. Before it, the busiest person came first and was read over the
full 150 days every time, so the round's top pages never fit a day's calls
(#1723).

## Commands

```sh
co rem investigate people --list                      # the order and the cost; nothing read or spent
co rem investigate people                             # the next 5, last 14 days first
co rem investigate people --limit 1                   # just the most recent correspondent
co rem investigate people --recent-days 7 --limit 0   # all queued people; last 7 days first
co rem investigate people --budget 20                 # stop new pages at 20 points; rerun for the rest
```

`co rem investigate people` is the command it always was; its order and
windows changed. It states the cost first — one model call a person, the mail
the map counted for the full investigations, how many are updates, and what
one full investigation measured on this machine — then investigates up to four
people at a time. It stops starting people at the weekly Codex budget, at this
run's `--budget`, or at the floor kept for your own work, and ends by saying
how many people are left. Already running pages finish after a stop. `projects`,
`orgs`, `skills` and `all` keep their order (most mail or sessions first). A
single page and `me` are unchanged.

## Order

People the owner wrote to at least once come first, then people who wrote
more than once and were never answered, then one-mail contacts (#1974). Within
each, the last `--recent-days` (default 14) first, then by the map's mail count
decayed by the weeks since the last mail. Left out: the owner (`investigate me`,
listed first while never investigated), addresses that may be the owner's,
automated senders, and vendors whose domain also sends notices. The overview
`co rem investigate` and `people --list` read the same queue. Counts are the
map's, a floor for what the 730-day read finds; see
[rem-investigation-correctness.md](rem-investigation-correctness.md).

## Windows: only what is new

| The person | Mode | Window read |
|---|---|---|
| Never investigated, or investigated but still unfinished and not in the last 7 days, with nothing newer | full | 730 days (`--days`) |
| Mail arrived after the page was last investigated | update | the days since that investigation |
| Investigated since their last mail | — | not in the queue |

"Last investigated" is the exact time this stage started that person's
investigation (`.state/people/investigated.json`), or, for a page investigated
another way, the date on its status line. So mail that arrives later the same
day is still new.

## What is new since the last run

`correspondents_since()` lists each connected mailbox **once** since the
previous run (metadata only: dates, senders, recipients) and matches the
addresses to people pages, instead of searching the server once per person.
The newest date per person goes to `.state/people/activity.json`, the cursor
to `.state/people/refresh.json`; both are owner-only (`0700` directory, `0600`
files) and hold no subject or body.

## Where the network is used

Nothing here gives the model the network. Every notebook run is confined
(Codex `--sandbox workspace-write`, no network; Claude Code `acceptEdits`), so
the model cannot call `co gmail` or `co outlook` itself. Everything that needs
the network is our code, before the model: the listing above, and the
investigation's gather — the private archive `co rem init` saved first, then
the server for mail it lacks, bodies and attachments — which #1942 writes into
the files the one turn searches with `rg`, `sed` and `ls`. Giving the run the
network would reopen what the confinement closed (`runner.harness_flags`); it
is not proposed.

## The daily round: four runs, two jobs (#1723)

Each scheduled run maintains first, as before. Then:

- **The first run of the local day finishes unfinished pages,** people,
  projects and organisations together, **most recent activity first,** within
  a reserved share of the day's calls (8). A person is one investigation over
  their window. A project or organisation takes the rest of the share and
  ends the portion, as before.
- **Every later run follows what is new:** the people the listing found with
  mail since the previous run (each read over only the days since their last
  investigation), and the projects with new messages you typed
  (`co rem projects write`'s path, `write_pages(since=…)`: an update from the
  new messages, or a first write only for a project active since the last
  run). At most 5 pages, one call each, within the day's call cap. A run with
  nothing new calls no model and says `nothing_new`.

Both stop starting pages at the weekly budget or the 70% floor, and both record
in `co rem logs` how many pages are left. Which run is which is decided by what
already ran today, not by the clock, so a machine asleep at the first slot
still gets its unfinished portion from whichever run comes first. The schedule
has six times by default; the first is the unfinished portion and the other
five follow new material, which costs nothing when nothing arrived.

## Measured

One real run on 2026-09-30, on this machine, against a temporary notebook
holding one fresh page for the owner's busiest recent correspondent, the same
person as #1850's baseline (157 mails in the 90-day map). Runner Codex,
`gpt-6-luna`, `co rem investigate people --limit 1` (a full investigation,
150 days), after #1942.

| | Before (#1850 / #1884, digest path) | This run (#1942's evidence files) |
|---|---|---|
| Material | 157 mails, 1.78M characters | 265 mails (129 Outlook, 136 Gmail) with 99 attachments, 2 coding messages; 1.85M characters in 366 files |
| Model calls | 31 (30 digest pieces + 1) | 1 |
| Input tokens | 8.2M | 1.93M (1.76M of them cached) |
| Output tokens | 503k | 56k |
| Time | 3 h 24 min | 15 min 3 s, gather included |
| Codex week | did not move off 8% | 25% → 26% |

The accepted page has all 11 sections, 88 citations over 17 sources, and 2
lines left `Unknown` (phone, company). The role on the page appears in only 2
of the 265 mails and was found and cited. No labelled phone number appears in
anything the person wrote in the window, so `Phone: Unknown` is the right
answer. An update for the same person reads only the days since this run.

For comparison, a people-only prototype of this stage (an evidence folder per
person with quoted threads capped at 4,000 characters, and a skill that told
the agent to stop after about 30 tool calls) wrote the same person's page in
0.67M input tokens and 5 min 40 s of model time, with 52 citations. It was
dropped so that there is one investigation path, #1942's; the gap is mostly
the quoted threads and attachments #1942 keeps whole.
