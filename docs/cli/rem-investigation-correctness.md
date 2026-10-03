# What an investigation may claim (#1974, problems 1, 2, 3, 9, 10)

1.9.0a2 on the owner's real notebook stamped pages "investigated" that the
model had never seen a mail about, ranked vendors above colleagues, threw a
whole page away for one miscopied citation, and ran a daily round that read no
mail. This page is the contract each of those now follows. The skill wording
(#1974 problems 6, 7, 8) and project identity (4, 5) are separate changes.

## 1. No stamp without material

An investigation gathers first and calls a model second. When the gather found
nothing about the subject — no mail body, attachment, session line or chat
message, and for a project no file to read under its Paths — the run stops
before any model call:

- the page is not changed and its status line does not gain `investigated`;
- the run record's outcome is `nothing_found`, with the coverage it searched;
- the message says what was searched and names the next step, e.g.
  `co rem investigate people/x.md --handle ADDRESS`.

**Nothing new since the last investigation (#1984).** A page investigated
before is read only over the days since then. When that window gathers nothing
-- no mail, attachment, session line or chat message -- the run stops before any
model call as well, for a project too: its file list is always there, and alone
it is not new material. The page and its status line are unchanged, the run
record's outcome is `nothing_new`, and the message says "Nothing new since
<date>" with what was searched, not a `--handle` to try (the handles found the
subject before). A person's empty pass is remembered in
`.state/people/investigated.json`, so the next run does not gather the same
empty window again; the daily round charges it no call and names it
`nothing_new` in the run's pages. 1.9.0a3 made a 92k-token turn for a person
whose window held nothing; its only change was deleting one Uncertainties line.

The same holds after digesting: on the summary tier, when every digest of the
material comes back empty, the synthesis turn is not run and nothing is stamped
(the digest calls already spent are recorded).

The validator is the backstop. A changed page whose every citation is the page
itself, the coverage note or the map (`investigation:page`,
`investigation:coverage`, `.state/map.json`) is refused: "cites only the page
itself and the coverage note".

**Pages already stamped wrongly.** A person or organisation page whose latest
recorded investigation (`co rem logs`) read nothing — no bodies, attachments or
messages, or "summarised in 0 chunk(s)" — is *hollow*. So is a page stamped
investigated whose Sources name no message, session, URL or file, only the
coverage note, the page or the map: the daily round keeps no per-page coverage,
and on the owner's notebook this is the one page (of five investigated) that was
written from nothing. The queue treats it as
never investigated: it is listed again, over the full window, and not skipped
as "investigated this week". No page is edited by hand; the next real
investigation replaces the stamp.

## 2. One people queue

`co rem investigate` (the overview), `co rem investigate people --list` and
`co rem investigate people` all read `people_pages.queue`, so their counts and
their first names agree.

Left out: the owner (see 3), addresses that may be the owner's, automated
candidates, any address that looks automated (no-reply, notifications,
billing…), and a sender the owner never wrote to whose domain also sends the
notices the map set aside (a vendor: `express@airbnb.com` when
`automated@airbnb.com` is a notice sender).

Order, in tiers:

| Tier | Who |
|---|---|
| 1 | people the owner wrote to at least once |
| 2 | people who wrote more than once and were never answered |
| 3 | one mail, never answered |

Within a tier, correspondents of the last `--recent-days` come first, then by
volume decayed by age: the map's mail count ÷ (1 + weeks since the last mail).
A colleague with 600 mails last week ranks above someone with one mail
yesterday.

**Counts are the map's.** The number beside a person is what the map counted in
its window (90 days by default), not what the investigation will read: that
reads 730 days by default, and the server search finds mail the map's listing did not
(one person showed 1 and had 617). The list and the cost line say so, and the
count reads as a floor ("at least 12 mails"). Singular counts are singular.

## 3. The owner's own page first

When the owner's page has never been investigated, `co rem investigate`
lists it first and its Next line is `co rem investigate me`;
`co rem investigate people --list` names it above the queue. Addresses the
owner wrote to many times and never heard from (likely the owner's own) are
shown with one command that confirms them all: `co rem init --mine a,b,c`.

Generated text says `co rem`, never `co wiki`: an owner page written by a
1.8.x map with `co wiki init --mine` in it is corrected on the next map.

A display name that is a header word ("From gws" — the owner's own test mail,
sent by a CLI that put that text in the To line) is not taken as a person's
name.

## 9. One bad citation drops one line, not the page

A candidate page is repaired before it is validated: a citation whose source
cannot be identified (or that has no entry under Sources) is removed.

- A line that cites it alongside a good citation loses only that marker.
- A line that rests on it alone is removed; a contact field keeps its label
  and becomes `Unknown`; a section left empty says `- Unknown`.
- Its Sources entry is removed.

`review.json` records `citations_dropped` and `lines_dropped`. The page is
accepted when what remains passes every other check; if nothing cited remains,
it is refused as before. Dropping was chosen over aliases (`[m12]`) because the
validator already decides which citations resolve, and dropping acts on that
decision without changing what the model is told (the skill wording belongs to
#1974 A).

The page Skills already say to link Company (a project's Organisation) to the
organisation page, but the turn was never told which organisation pages exist.
Now a person's turn is handed the org pages whose Domains hold one of their mail
domains (or a parent domain), and a project's turn the notebook's organisations
(`investigation:org-pages`, context, never evidence). After the turn, a person
page whose `Company:` names an organisation page's title exactly is linked to it
by code as well.

## 10. The daily round reads mail

Notebooks made before init subscribed its mailboxes (#1946) have Gmail and
Outlook connected but switched off. `co rem status` and `co rem doctor` now say
so per mailbox with the fix:

| Mailbox state | Said |
|---|---|
| not connected | `co auth google` / `co auth microsoft` |
| connected, not subscribed | the daily round does not read it: `co rem sources add gmail`, then `co rem start` |
| subscribed, not approved | waiting for your approval: `co rem start` |
| subscribed and approved | read by the daily round |
| removed by you | skipped, as you asked |

`co rem start` offers every connected mailbox that is neither subscribed nor
removed: the summary lists it as "connected; read from now on if you approve".
Approving subscribes and approves it; declining changes nothing. Nothing is
switched on without that answer.

**Stale run records.** A run record still `running` whose process is gone (same
machine) or, for records without a process id, older than its runner timeout
times its attempts plus an hour, is marked `abandoned` with the reason, by the
next run that writes (sync, the daily round, an investigation). `status` and
`logs` stay read-only.

Maintenance does not write the status line (`restore_runner_fields` keeps the
runner's); a maintained page's `not investigated yet` is accurate about the
investigation pass and is left as it is.

## Private copies

A task folder under `.state/tasks/` holds a copy of the owner's mail while a
turn runs. Files there are created `0600` (the stage runs under umask `077`,
the model's subprocess included). #1970 already removes a finished task's
copies; now a task interrupted by Ctrl-C is scrubbed too, a folder a killed run
left without `result.json` is scrubbed once it is older than six hours, and
kept files are set to `0600`. The routed investigation's original-evidence copy
(`.state/evidence/<id>.json`) is deleted when the run ends, like the evidence
directory.

## Lines that misled

- `co rem config`: Next is `co rem status`; an unchecked tier says, in its note,
  which command checks it — the Next line no longer reads as "set the model".
- `co rem logs --usage`: runs recorded before the model was stored count under
  `unrecorded`, not `?`; tokens per 1k input characters is computed only over
  runs that recorded their input size.
- pypdf's parser warnings no longer print in the terminal.
- `co rem --help` lists `projects` among the advanced commands.
- The model's `co ai` runs with the caller's `PYTHONPATH` made absolute. A
  relative `PYTHONPATH=.` (a development checkout, or the schedule it wrote)
  resolved against `.state/tasks`, imported an older installed connectonion,
  and failed with "Skill 'rem-investigate' not found" after minutes of
  gathering. A source checkout running co rem is also put on the child's
  PYTHONPATH, since `python -m` found it by cwd alone. Investigation now checks
  the skill is reachable from the task folder before gathering. An installed
  schedule keeps the `PYTHONPATH` it was written with until `co rem start`
  writes it again.
- The launchd label was already `ai.openonion.co-rem.<hash>` since #1932, and a
  `co-wiki` job is replaced on the first `co rem` command; nothing to change.
