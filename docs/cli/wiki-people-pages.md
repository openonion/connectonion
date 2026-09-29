# People pages from a search of their evidence (#1943, stage 3)

A person's page used to be written by reading *all* of their mail through
chunk digests before a word of the page was written. On the owner's notebook
that cost 8.2M input tokens and 3 h 24 min for one 157-mail correspondent
(#1850, #1884), and the daily round never reached the people who mattered,
because their pages never fit a day's calls (#1723).

This stage investigates a person the way a person would: a script puts
everything the notebook holds about them into one folder with an index, and
an agent searches that folder for what each section of the page needs, reads
the few items that answer it, and writes the page. Recent correspondents come
first.

```text
  mailboxes (Gmail, Outlook)   .state/mail archive   WhatsApp files   your coding messages
                 │   1. script, no model: fetch what is missing, then file it
                 ▼
  .state/people/<page>/index.jsonl, state.json        (0700 / 0600, owner-only)
                 │   2. copy this person's items into one task folder
                 ▼
  .state/tasks/people-…/evidence/index.md + mail/ attachments/ chats/ sessions/
                 │   3. one model call: search with rg / sed / ls, read what matters
                 ▼
  people/<page>.md                                     (validated, then saved)
```

## Commands

```sh
co wiki investigate people --list                   # the order and the cost; no model, no mail read
co wiki investigate people                          # the next 5, last 14 days first
co wiki investigate people --limit 1                # just the most recent correspondent
co wiki investigate people --recent-days 7 --limit 0   # everyone written to this week
```

`co wiki investigate people` is the command it always was; what it runs
changed. It lists people pages that are unfinished (still carrying `Unknown`)
or have mail they were not written from, orders them by the date of the last
mail with them, the last `--recent-days` (default 14) first, and takes the
next `--limit` (default 5). For each one it first prepares the evidence (the
script, step 1 below), then states the cost of the portion — model calls,
characters sent, and what the evidence folders hold — and only then starts the
model, one person after another. It stops starting people when the weekly
Codex budget, this run's `--budget`, or the floor kept for your own work is
reached, and it ends by saying how many are left.

A single page, `co wiki investigate people/<page>.md`, still takes the older
path (#1850's evidence files once #1942 lands); `me` is unchanged.

## Step 1: the evidence (a script, no model)

Everything that needs the network happens here, in our own code, before the
model starts. Per person, bounded and incremental:

1. **Addresses.** The person's addresses from the map (`.state/map.json`) and
   the `Email:` line of their page, minus every address that is the owner's.
2. **Saved mail first.** Messages already saved by `co wiki init`
   (`.state/mail/people/<hash>.jsonl` → `.state/mail/messages/...`) and rows of
   the source inventory that name one of the addresses.
3. **Then the server, for what is missing.** For each connected mailbox, one
   search per address (`list_with`: Gmail's `from/to/cc`, Outlook's
   `participants:`) over the window not yet searched: the last 90 days
   (`--days`) the first time, and from the last search (less one hour) after
   that. Every body not yet saved is fetched and saved in the same private
   archive init uses, at most 300 a person a run; attachments of newly fetched
   mail are saved and their text extracted, at most 40 mails a run.
4. **Local sources, no network:** WhatsApp lines from the chats you chose
   (`co wiki sources add whatsapp --chat`) whose sender or chat is this person,
   and your own Codex / Claude Code messages (`.state/projects/`) that name the
   person by full name or address. OneNote has no local export here yet; the
   coverage says it was not read.

The person's private record lives in `.state/people/<page>/`:

| File | Holds |
|---|---|
| `index.jsonl` | One row per item: source id, kind, date, from, to, cc, subject, and where its text is. No mail bodies (those stay in `.state/mail/messages/`); a WhatsApp line or coding message, a few hundred characters, is kept inline |
| `state.json` | Addresses, when each mailbox was last searched, last activity, and `written_through`: the newest item the page was written from |

For the model run, this person's items are copied into the run's own task
folder as plain text: `evidence/index.md` (one line per item: date · kind ·
from → to · subject · source id · file · size) and one file per item, each
opening with `### <source id> · <date> · <sender>`. A mail keeps its own reply
in full (up to 20,000 characters) and at most 4,000 characters of the quoted
thread below it, after a line that says so. After the run the copies are
deleted; `evidence/index.md` stays with the task record.

## Step 2: the page (one model call)

One call per person, through the configured runner (`co ai --harness codex`
by default), with the `wiki-person-search` skill (how to search the folder)
and the `wiki-page-person` skill (the page's shape). The prompt carries the
two skills, the page as it stands, the coverage note and the index; the
evidence files stay on disk for the agent to search with `rg`, `grep`, `sed`
and `ls`. The skill asks for about 30 tool calls and tells the agent to read in
full only what a section needs.

The page passes the same review as every investigated page: canonical
sections and contact fields, every citation pointing at a source id in the
index, the owner's addresses removed from someone else's page. One check is
new: a candidate that copies 200 or more characters of any mail verbatim is
refused, because a page is shareable and someone's mail is not; a phone
number or a deadline is a fact to cite, a paragraph is not. An accepted
page's status line gains `investigated <date> (evidence search: gmail,
outlook, …)`, and `written_through` moves to the newest item. A refused page
is kept beside its task with the reason, and nothing moves.

- **First write:** every item in the index.
- **Update:** only the items after `written_through`, with the page as it
  stands. A person with nothing new is not investigated again.
- **No material at all:** no model call; the page is skipped and says so in
  the output.

### Why the model does not call `co gmail` itself

The owner's design says the investigating agent knows the command line
(`co gmail`, `co outlook`, `co onenote`, `co whatsapp log`) and uses it. It
cannot, unattended: every notebook run is confined (Codex
`--sandbox workspace-write`, no network; Claude Code `acceptEdits`, no reads
outside its task folder), because the material it reads is mail anyone can
send the user, and an agent with a shell, the network and the user's logged-in
mailbox is exactly what a hostile mail would want. So the split is:

| Where | Does |
|---|---|
| Script, before the model (our code, network allowed) | Searches the mailboxes for the person, fetches missing bodies and attachments, reads the local WhatsApp files and coding messages, writes the evidence folder |
| Model, inside the sandbox (no network) | Searches that folder with `rg` / `grep` / `sed` / `ls`, reads what matters, writes one candidate page |

Giving the run network access would reopen the hole that confinement closed
(`runner.harness_flags`); it is not done here.

### Measured

One real run on 2026-09-30, on this machine, against a temporary notebook
holding one fresh page: the owner's busiest recent correspondent, the same
person as #1850's baseline (157 mails in the 90-day map). Runner Codex,
`gpt-6-luna`, `--days 150`.

| | Before (#1850 / #1884, digest path) | This path |
|---|---|---|
| Material | 157 mails, 1.78M characters gathered and all digested | 265 items (mail and attachments over 150 days), 269 files, 573 KB on disk; the agent chose what to read |
| Model calls | 31 (30 extract pieces + 1) | 1 |
| Input tokens | 8.2M | 0.67M (0.57M of them cached) |
| Output tokens | 503k | 27k |
| Time | 3 h 24 min | 92 s script (search, 265 bodies, attachments of 40 mails), then 5 min 40 s model call |
| Codex week | did not move off 8% | 24% → 25% |

The prompt carried 74,408 characters: the two skills, the page and the
265-line index. The accepted page has all 11 sections, 52 citations over 12
sources, and 3 lines left `Unknown` (phone, company, signing entity). The
role on the page appears in only 2 of the 265 mails and was found and cited.
No labelled phone number appears in anything the person wrote in the window,
so `Phone: Unknown` is the right answer, not a miss. After the run the task
folder held no evidence copies, only `evidence-index.md`.

One earlier attempt failed in under a second, before any model turn: the
measurement shell set `PYTHONPATH=.`, and the runner starts `co ai` from the
task folder, where `.` is not the checkout. Nothing in the product changed for
it; the evidence the script had already saved was reused by the second attempt.

## Order and portions

People are ordered by the date of the last mail with them — the newest of the
map's `last` and the newest item in their evidence — with the last 14 days
first, then everyone older, newest first. Left out, as before: the owner
(`investigate me`), addresses that may be the owner's, automated senders, and
a page investigated in the last 7 days that has nothing new.

The same order is `connectonion.wiki.people_pages.queue()`, so the first run
can take the people of the last two weeks before anyone older.

## The daily round: four runs, two jobs (#1723)

The schedule's runs (`schedule.times`, six by default: 03, 04, 06, 17, 18
and 19 o'clock) each maintain first, as before. Then:

- **The first run of the local day finishes unfinished pages.** It walks the
  unfinished people, projects and organisations, **most recent activity
  first**, and investigates as many as fit its share of the day's calls (8 at
  most). A person is one call. A project or organisation takes the older
  path and ends the run's portion.
- **Every later run follows what is new.** Only people and projects with new
  material since the previous run: a person with new mail is updated from the
  new mail only; a project with new messages you typed is updated from those
  only (`co wiki projects write`'s path). At most 5 pages a run, one call
  each, within the day's call cap. A run with nothing new calls no model.

Both stop starting pages at the weekly Codex budget or the 70% floor, and both
record, in `co wiki logs`, how many pages are left. Which run is which is
decided by what already ran today, not by the clock, so a machine asleep at
03:00 still gets its unfinished portion from whichever run comes first.
