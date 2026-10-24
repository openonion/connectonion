# co rem — command guide

**Start in one command:** `co rem init` maps the last 180 days and investigates
every eligible page. Run `co rem status` to see coverage and `co rem open` to
read it. A refused page stays visible in the run history with its retry command.

Jump to [Start here](#start-here) · [Commands](#commands) ·
[Source controls](#source) · [Scheduling](#scheduling-and-accounting) ·
[Reader layout](#what-the-reader-shows).

Check your installed release. The exact commands are
also available through `co rem --help` and each subcommand's `--help` page.
Old command names (`unfinished`, `people`, `daily`, `subscribe`, `subscriptions`,
`unsubscribe`, `route`, `usage`) remain aliases in 1.9.0 and print their new name.

## What it is

**co rem enables decentralized context flow.** It connects context from your
mail (connected with `co auth google` or `co auth microsoft`) and your local
Codex and Claude Code sessions in linked Markdown pages about people,
projects and tools. Those pages stay on your machine, with links back to
the evidence. You and your agents can read and reuse them in the next task.
Memory keeps context available over time; carrying context through your
work is the purpose.

The notebook is a folder on your machine, `~/.co/rem`. Saved mail bodies stay
in its owner-only `.state/` and never go into a page; a model reads them only
through the login you choose. By default it runs on your own Codex plan
(`gpt-6-luna`, your ChatGPT sign-in), or on Claude Code (Sonnet) when Codex is
not installed or not signed in, and spends no OpenOnion credits. A notebook
keeps the runner saved in its `config.yaml`; change it with
`co rem config set runner claude-code`.

What it costs, measured: the first run writes up to 16 pages at a time. An earlier
real notebook trial wrote 198 of 242 people, project and organisation pages in
about 25 minutes. Init has no REM page or weekly quota cap; the scheduled daily
round still uses a 35-point budget and a 90% weekly safety floor. The model
provider may enforce its own limits. `co rem status` shows the routine limits.
Investigating a very large subject can still cost millions of tokens; searching
instead of summarising is
[#1850](https://github.com/openonion/connectonion/issues/1850).

## Coming from co wiki (1.8.8–1.8.9)

1.9.0 renames the feature `co rem` (#1932). Nothing needs doing by hand:

- The first `co rem` moves `~/.co/wiki` to `~/.co/rem` and says so in one line.
  If both folders exist it refuses, names both, and merges nothing. An explicit
  `--root` is used as given. A move that fails leaves the old folder whole.
- A daily schedule that `co wiki start` installed is replaced by one that runs
  `co rem sync`, the next time `co rem` runs for that notebook.
- `co wiki …` runs nothing in 1.9.x: it exits 2 with `co wiki is now co rem.`
  and one `Next: co rem …` line with the same arguments. It is removed in 1.10.
- `CO_WIKI_PROGRAM` is still read when `CO_REM_PROGRAM` is not set, with a
  one-line notice. `pip install 'connectonion[wiki]'` still installs the
  spreadsheet extra, now called `rem`.

## Start here

```bash
co rem init                 # Map sources, then investigate your people, work and installed skills
co rem open                 # Read your page
co rem start                # Reapprove changed sources or resume a stopped daily round
```

The first run is one command (#1943). `init` first maps 180 days of
mail and your local Codex / Claude Code sessions, saves the private mail
material, and prints your own page's facts — who you write to most, how much
mail, which projects you have been coding in — with the page's path, within the
first minutes. Then it uses the configured model to write your own page: the whole
`investigate me`, from everything you sent and your coding sessions of the last
30 days (or `--days`), one model turn over evidence files, about 15 minutes.
It writes a quick first pass of your page in about 4 minutes, then the whole
page alongside the selected pages. Next come all eligible mapped people, recent
first, each investigated from up to two years of their mail; queued projects
already listed in the map, recent first; all pending mapped organisations; and
installed skills from source and retained run evidence: 16 pages at a time.
After the map summary, init prints your notebook languages and whether they
were detected from your sent mail and typed sessions or set in config. Use
`co rem init --languages zh,en` to set them before mapping, or
`co rem config set languages en` to change them later. English remains the
canonical writing language. After tidying and drawing decisions and principles,
init translates every listed, written page into your first non-English language,
even when English is first in the list. Mapped-only stubs and the skill catalog
index are excluded. `--no-translate` skips this last step; `--no-investigate`,
`--estimate-only`, English-only languages or an unavailable runner also skip it
with a reason in JSON. JSON includes `languages` and a `translation` summary.

The estimate includes one translation per selected page plus your page, with
unknown decision/principle counts treated as zero. Translation uses its own
`limits.workers` lanes after the investigations, so its wall time is added to
the page queue. Completed translation runs in this notebook supply median rates;
otherwise planning uses 80,000 input tokens and 35 seconds per page (measured
2026-10-21). First-run translation has no daily cap.

Session folders discovered after the map summary remain
unmapped candidates during this first run. They do not silently add project
pages or change the project count the owner just saw.
Init rereads the retained project-message window against the current map. If
you widen `--days`, older newly mapped folders get their existing messages;
message IDs prevent duplicates. Daily extraction stays incremental.
An earlier whole-notebook experiment wrote 199 of 242 pages in about 30 minutes
and moved the Codex week by one point. A person page
read 150 days at the time; a real contact went back 15 months, so the window is
now two years. The mail is searched, not pasted: a wider window widens what the
model can find, not what every turn reads. `--first-people N`,
`--first-projects N`, `--first-orgs N` and `--first-skills N` cap a kind (0 for none).

For a historical census, `co rem init --all-history --investigate-all
--estimate-only` lists connected mail metadata since 1970 and local session
history, then forecasts every mapped person and project without a model turn
or body archive. Yearly mail listings still split past the provider cap; a
timeout is retried in smaller windows and any missing day is marked incomplete.
Completed years remain in a lower-bound map if a later connection fails; the
failed remainder is marked incomplete and a retry may still rescan it.
The People reader also shows one-off correspondents in a separate searchable
directory, labelled as unreviewed contacts rather than as established people.
`--investigate-all` also enables the historical map when used alone. Without
`--estimate-only` it selects all eligible mapped pages without a REM quota stop.
Each person currently retains its
per-page source window; reading back to the first mapped message is tracked in
draft PR #2209. An all-history map archives only the most recent 180 days of
mail bodies; older material is fetched for a selected investigation.

Before it spends anything it says one total (#2008): which runner and model,
that it runs on your own plan, and "About N pages (...), ~X billed input tokens,
~Y minutes (an estimate ...)". Per page it is the median of this notebook's own
completed runs of that kind (`.state/runs/`). Before there are any, it uses
measured rates, heaviest pages first, because each queue starts with its most
active pages. The first ten people, three projects and two organisations cost
what the 2026-10-20 release check measured on a fresh 180-day notebook (16
workers, Codex at fast speed): a person 6.3M input tokens and ~35 minutes
including its deepening pass, a project 2.7M and ~11 minutes, an organisation
8.0M and ~59 minutes. Every page after those costs what the 1.9.2b1 full run
measured: a person 2.85M and ~11 minutes, a project 630k and ~2 minutes, an
organisation 2.0M and ~8.5 minutes, a skill 800k and ~3 minutes. Each owner
turn is 6.5M and ~35 minutes; the quick and full turns are both counted. The
full-run rates alone announced ~42 minutes and ~50M tokens for the release
check, which took 82 minutes and 102M; the estimate now says 95 minutes and
100M. It does not predict every retry or refusal. Minutes are
wall clock: after the quick owner turn, the
full turn and selected pages share `limits.workers` workers (default 16),
the same setting as `co rem investigate CATEGORY`. The estimate simulates
that queue so a slow last page is not hidden by an average. Init starts every
selected page and keeps going after individual refusals; there is no REM quota
gate on this foreground run. A model provider may still refuse new turns at its
own limit. Before the first page, init runs one source-free turn against the
selected model. If access is denied, it keeps the map and mail archive, reports
the login or model change to make, and leaves background upkeep off. If access
expires while pages are running, in-flight pages finish and the remaining queue
stops. The input-token estimate includes cached tokens
and is not weekly quota points. Ctrl-C stops it, says which pages
were written, keeps the map and every page, and names the command that
continues. It skips the model steps, with a one-line reason, when
the runner is not installed or not signed in (checked before the map starts,
without a model), when no mailbox gave an address of yours, when your page was
already written. `--json` and non-terminal runs investigate by default too.
`--no-investigate` explicitly builds the map only. Later new evidence can be
investigated with `co rem investigate all`.

Your page is titled with what you are called: `--name` if given, else the
name the people writing to you put on your address (the To and Cc of mail you
received; spellings that differ only in case are one name, and a name that is
just the address, `xietianle`, is not one), else the From name of mail you
sent, else the name a mailbox has configured (#2008). On the owner's real
account the configured name was "Aaron x", and Outlook stamps it on every sent
mail too; correspondents wrote "Aaron Xie". A new notebook names the file after
you (`people/aaron-xie-….md`); an existing page keeps its path.

Progress shows the mail scan and body archive counts, then a live total bar and
completed counts for You, People, Projects, Organisations and Skills. Each page
prints a result line. The scan steps are kept in `.state/init-progress.log`.
Addresses that look like yours (you wrote,
nobody replied) are listed on one line with one command that confirms the ones
you keep: `co rem init --mine a@example.org,b@example.org`. Mailboxes init read
are subscribed, so `co rem start`'s summary lists them as sources to read; start
still asks before anything is read in the background.

To fill other pages, `co rem investigate` lists what is left, by category, and
runs no model. Copy the `Next:` command printed by `investigate` to investigate one existing
page. You can also supply an exact title or email when it identifies one page,
for example `co rem investigate 'Corin'` if that person exists in your notebook.
Ambiguous names list the matching paths and do not start a model. Example page
names in old help text, such as `people/elodie.md`, are not built-in records.
`--help` displays help and exits, even when you also supply a page name.

```bash
co rem investigate          # What is left to investigate, by category; no model
co rem investigate PAGE    # One page; a page refused before is retried on the same sources
co rem investigate me --quick --days 5  # Bounded first pass; disclose uncovered sources
co rem open                 # Open a fresh snapshot of the notebook in your browser
co rem sync --dry-run       # Inspect pending metadata, without running a model
co rem sync                 # One update: new material, then at most one unfinished page
co rem logs                 # Inspect results, partial coverage and failures
```

Normal output uses readable labels and plain page paths. Empty lists explain
what is missing; unknown usage remains **Unknown**, never zero. Results end
with a copyable `Next:` command, including the selected root and shell quoting.
Use `co rem --help` as the workflow guide: it gives task selection,
observed inputs, expected results, source/quality checks and recovery before
the command inventory. `init --help`, `investigate --help` and `sync --help`
explain their full workflow as well as options. The overview and group help
share one implementation, so human and agent guidance cannot drift separately. Root and JSON flags belong **before** the subcommand:

```bash
co rem --root '/path/to/my co rem' investigate
co rem --root '/path/to/my co rem' --json status
```

Explicit `--json` retains the `ok`, `data`, and `next` envelope for scripts.
No-argument `--json` continues to return status, without the human guide.
Piping human output does not hide the next step. Grouped help covers:

| Task | Commands |
|---|---|
| Map and investigate | `init`, `investigate`, `map-skills`, `scan`, `stub` |
| Browse | `open`, `list`, `show`, `search`, `status` |
| Update and review | `sync`, `capture`, `reflect`, `reflections`, `propose`, `review`, `abstract` |
| Sources and background | `sources`, `sources add`, `sources remove`, `start`, `stop` |
| Settings and diagnostics | `config`, `config set`, `logs`, `doctor` |

After the first run, `init` offers the same source and schedule approval as
`start`, then installs background maintenance without repeating the first sync.
In a script, `init --yes` supplies that approval; without it the foreground
result remains available and scheduling is deferred. `init --no-start` leaves
background work off, and `init --estimate-only` never grants consent or schedules.
If a selected page fails or is refused, init reports a nonzero exit and leaves
nightly upkeep off until the unfinished pages are repaired.
`start` can reapprove changed sources or resume a stopped schedule. The daily
round investigates at most one unfinished page per local day when its call
budget allows.
A mapped page is not an investigated or quality-approved page.
For an initial trial, `co rem init --days 5` investigates your page over the same
five-day window. `investigate me --quick` is the older bounded pass: it samples
recent evidence, takes one synthesis turn, and marks its coverage as partial.
init uses the quick pass first so a useful owner page arrives early, then runs
the full pass with the other selected pages.

## Installed-skill skeletons at initialization

`co rem init` deterministically builds People, Organizations, Projects and Skills pages from
their canonical templates and available source metadata before any model
investigation. Unknown fields remain explicit; investigation is a separate step.
See the [initialization interaction contract](rem-init-contract.md).

Its coverage lines keep the four source states apart, because each one needs a
different next command:

```text
gmail: metadata only, 90 days; a seven-day window at the 200-message listing cap is split until every message in it is listed; 42 correspondents
outlook: not connected; not searched. Connect it with co auth microsoft
codex: /home/you/.codex/sessions — scanned; no sessions in this window
claude-code: /home/you/.claude/projects — disabled; not scanned
```

A mailbox that was read and held nobody, one nobody has connected, one the user
unsubscribed, and one that is connected but would not open are four different
answers; so are a session directory that is missing, one switched off, and one
scanned that had nothing inside the window.

Where init can see that an address is probably the user's own — mail goes to it
repeatedly and nothing ever comes back — it says so and prints the exact
`init --mine <address>` that confirms it. It never merges on the guess: an
assistant and a family member look the same from the headers.
The map can also be run independently:

```bash
co rem --root /private/path/to/rem map-skills
co rem --root /private/path/to/rem map-skills --skills-dir /known/project/.co/skills
```

The generated `skills/catalog/index.md` links to **one page per skill name**
(#1974). A skill installed three times — in `~/.claude/skills`, `~/.codex/skills`
and `~/.agents/skills` — is one page, not three. The page links to the source
file instead of pasting it, and keeps the frontmatter facts short: the name, the
description, the allowed tools. Its `Source` section, which the map owns and
rewrites on every run, lists each copy:

```text
## Source
- File: /home/you/.claude/skills/ship-feature/SKILL.md
- Discovery: claude-user
- Allowed tools: Bash, Read
- Content: sha256 3f2a9c1e04b7; 3 installed copies
- Also installed at: /home/you/.codex/skills/ship-feature/SKILL.md (identical)
- Also installed at: /home/you/.agents/skills/ship-feature/SKILL.md (differs: sha256 77b0d2e41f9a)
- Status: mapped from metadata; behavior not verified
```

Copies are compared by content hash, so a copy that has drifted says so. A copy
in a temporary or package location — a git worktree (`.claude/worktrees/`,
`.worktree/`, `.worktrees/`, `.codex/worktrees/`), `site-packages`, a plugin
cache — never becomes the `File` of a page and never
makes a page of its own; it is listed as `Also installed at` on the page of a
copy that lives somewhere real. A name found only in such places is listed in
the index under "Only in temporary or package locations", without a page.

`Usage history` opens with what your own coding sessions say, counted by a
script with no model: how many times the skill was invoked and when last.

```text
- Invoked 14 times in your coding sessions in the last 180 days, last on 2026-09-28 (Claude Code 9, Codex 5). ...
```

Claude Code counts a `Skill` tool call and a `/skill-name` command; Codex counts
a `$skill-name` in a message you typed (read as `sync` reads it, Codex Desktop
included) and a tool call that reads the skill's
`SKILL.md`, once per turn. co rem's own runs are not counted. An invocation is
not a completed run: `Current status` and `Performance` still wait for run
evidence. Counts are cached per session file under `.state/skill-usage.json`,
so a rerun reads only what changed.

The reader calls these **skill-name matches**: invocation attempts in coding
sessions matched by name. `Run evidence` counts retained evaluation attempts
separately; it may show zero even when coding sessions contain name matches.
Neither count proves that this installed version ran or that the task succeeded.
The Skills list uses a compact usage count and last date; the skill page keeps
the match details, scope explanation and usage bar.

Rerunning the map (`init`, `sync`'s map, or `map-skills`) moves an older
notebook to this shape. Pages made one per copy are merged into the name's page:
a page with written content keeps it (sections are merged line by line, citations
renumbered), the pasted `SKILL.md` snapshot is removed, and the old page is
moved to `.state/archived/` — never deleted. Its record becomes an **alias**
(`.state/aliases.json`): links to it in other pages are rewritten, and a command
given the old name opens the merged page. A page whose only source was a
temporary copy and that holds nothing but map output is archived the same way.
Original `SKILL.md` files are never changed or run, and `skills/approved/`
remains write-protected.

Defaults cover the co/Claude skill search roots, conventional agent/Codex skill
roots, and co ai's bundled default allowlist. This is a shallow inventory, not
an exhaustive plugin-cache or remote-catalog scan. Repeat `--skills-dir` for
explicit roots; supplying it replaces defaults for that scan. Coverage and
unreadable files are reported in the index and command result.

The [co rem CLI reference](https://github.com/openonion/connectonion/blob/v1.9.0/connectonion/useful_skills/rem-init/CLI.md) explains
mail IDs, browser tabs, source/working/output directories and failure recovery.

## One execution path

```text
User / scheduler
      |
      v
co rem init / investigate / sync / abstract
      |
      | stage Skill + source Skill + page shape + material paths
      v
co ai --json --harness <codex | claude-code | ours> /rem-<stage>
      |
      +-- Codex tool       --> Codex subscription
      +-- Claude Code tool --> Claude Code subscription
      +-- COAI agent       --> configured LLM provider (including Ollama)
      |
      v
Markdown pages + reported usage + observed file changes
```

COAI already delegates before creating its own LLM loop. Selecting Codex
therefore does not spend a COAI model turn deciding to delegate. All co rem
stages, including extraction and maintenance, use that same command.

co rem's former app-server subclass, dynamic rem_* tools, isolated Codex HOME,
auth-file copying, native version/config checks and direct native extraction
path have been removed. The shared COAI native adapters remain: their job is
to speak Codex or Claude Code's protocol once for all callers.

co rem retains source importers, bounded digest batches, page templates,
identity roster, progress, sync locking/accounting, OS scheduling and the
reader. A shell can call the public CLI; rewriting these data operations as a
second shell implementation would duplicate behavior.

## Commands

Group options precede the command: `co rem --root /path/to/rem --json list`.
Every command returns a next command, including in JSON and through a pipe.

| Command | Behavior |
|---|---|
| `co rem init` | Discover sources and map pages, then use the configured model to investigate your page, all eligible people, queued projects, pending mapped organizations and installed skills, recent first. `--no-investigate` explicitly stops after the map. |
| `co rem scan people --days 150 --min-mails 1` | Enumerate correspondent signals from Gmail/Outlook; no model. Repeat `--mine <address>` for own addresses. |
| `co rem scan orgs --days 180 --min-people 2` | List work domains that two or more people write from — where an organisation page earns its place. No model. |
| `co rem scan projects --days 150` | Enumerate session working directories and local Git repository identities; no model. |
| `co rem import sessions --days 30` | Agent sessions: one page per Codex or Claude Code conversation you typed in, under `sessions/`, linked to the project whose folder it ran in (a worktree counts as its repository). Your typed messages and the final reply, with what the session produced (pull requests, commits, branches, changed files). No model. Automation, harness prompts, subagents, `/tmp` probes and REM's own runs stay out; init and sync run it. |
| `co rem import sessions --summarise` | Also ask the configured model, eight sessions per turn, for each session's title, summary, topic tags, outcome, your decisions (kept only when quoted word for word) and open follow-ups. `--limit` caps it (default 40). The reader's **Agent sessions** list searches and filters them. |
| `co rem stub person "Alice" --email alice@example.org --handle 艾丽丝` | Create the canonical person skeleton if absent. |
| `co rem stub org "UNSW" --domain unsw.edu.au --person people/rowan-ashdown.md` | Create an organisation skeleton; `People here` holds links, not copies. |
| `co rem stub project "Aurora" --path /path/to/repo` | Create a project skeleton. |
| `co rem list people --aliases` | Existing identity roster: page, title, aliases, addresses, relationship summary. |
| `co rem list people --review` | Pages held for review: titled by an address the owner never wrote to, or only ever wrote to. |
| `co rem investigate people/alice.md` | Read the existing page, gather sources, digest oversized material, fill that same page through the Skill. |
| `co rem investigate` | What is left to investigate, by category, most useful first. No model. |
| `co rem investigate people --limit 3` | Investigate the next three people, the last 14 days' correspondents first (`--recent-days`): a person investigated before reads only the mail since then ([details](rem-people-pages.md)). `--list` prints the order and the cost and runs nothing. `projects`, `orgs`, `skills` take unfinished pages, most mail or sessions first. |
| `co rem investigate me` | Fill your own page from what you sent and your coding sessions of the last 30 days. |
| `co rem enrich people/alice.md` | Follow the leads a page has not followed — links, attachments, older threads — and add what they establish. One model turn with the `rem-enrich` Skill, the page's cited originals and a reading ledger of every source the saved archive holds about the subject (no live mailbox query). Prints the lead list: followed, open, blocked. [Details](#deepen-one-page-enrich-and-muse). |
| `co rem muse people/alice.md` | Think one page through: ask many questions, study the five best, write only on insight. One thread of seven resumed turns with the `rem-muse` Skill. [Details](#deepen-one-page-enrich-and-muse). |
| `co rem deepen --pages 2` | Deepen the highest-value thin pages, one enrich then muse round each, within a separate weekly budget. [Details](#deepen-over-time-co-rem-deepen). |
| `co rem abstract` | Run rem-abstract over existing notebook evidence. |
| `co rem start` | Confirm source access, run first bounded sync, install macOS background schedule. Asks again whenever anything its summary shows (sources, runner, model, permissions, schedule, limits) changed since the last approval. A start after `stop` resumes the schedule without a batch; `co rem sync` runs one. |
| `co rem start --yes` | Explicit noninteractive consent for start. |
| `co rem stop` | Remove that notebook's background job; preserve pages and progress. |
| `co rem sync` | The whole update: one batch of new material; then the day's first run investigates unfinished pages, most recent first, and every later run updates only the people and projects with something new. What the schedule runs (`sync --scheduled`). |
| `co rem sync --source codex --dry-run` | Pending metadata only; no model or source body reads. |
| `co rem sources add codex --project /path/to/repo --since 30d` | Save a scoped source choice. |
| `co rem sources add whatsapp --chat <id>` | Read one WhatsApp chat (group or person) from the files `co whatsapp listen` keeps; ids from `co whatsapp chats`. Repeat per chat; the next `co rem start` shows it and asks before anything is read. `co rem sources remove whatsapp --chat <id>` stops one chat. |
| `co rem sources remove codex` | Disable that source. |
| `co rem list people` / `show people/alice.md` / `search Alice` | Inspect Markdown without model calls. |
| `co rem status` / `sources` / `config` / `logs` / `logs --usage` / `doctor` | Inspect configuration, progress, diagnostics and reported usage. |
| `co rem open` | Render a fresh self-contained HTML snapshot to a temporary file and open it. Works offline; prints the file path and a `file://` link. |
| `co rem open --live` | Open the live view in O Chat, read from your `co ai` Host over OIP. Reuses an online Host or starts `co ai` automatically in the background, without channel listeners or an extra chat tab. Opens live REM only after readiness; failure names `.co/rem-live-host.log` and labels the snapshot fallback. Default notebook only; `--no-launch` still starts the Host but only prints the URL. |
| `co rem open --no-launch` | Print the page without opening the browser. |

Until 1.8.9 the default opened `https://chat.openonion.ai/<address>/wiki` before
O Chat served that route, so the page never loaded (#1828). O Chat serves it
since openonion/oo-chat#246; opening locally stays the default because it works
offline and needs no Host, and the live view is asked for with `--live`.
New live links use `https://chat.openonion.ai/<address>/rem`; old `/wiki` links
redirect to `/rem`. The route and both switches live in `connectonion/rem/reader.py` (`LIVE_REM_URL`,
`LIVE_REM_SERVED`, `LIVE_IS_DEFAULT`). `--local` is still accepted and always
means the snapshot. If the live view says co rem is not yours, add the
browser's address as an admin of the Host: `co trust admin add <address>`.

The page reads each record for what it knows (#1836). A page carries one of
three tags: **Mapped** (an outline from your sources; its status line still says
"not investigated yet"), **Partly investigated** (some sections filled from sources; the rest
not investigated yet) and **Investigated**. "Unknown" lines and placeholders are not shown;
the headings still empty are named once at the foot of the page with the
`co rem investigate '<page>'` command that fills them. Lists put pages with
findings first, then newest last contact. The Markdown file is unchanged, and
**Copy Markdown** at the foot copies it as written, unknowns included.

### Deepen one page: enrich and muse

`investigate` writes a page from what its gather found. Two commands go further
on one page that is already written, each through the same `co ai` runner and
the same review gate as investigate (citations trace to a source, every quote is
word for word in the source it cites, contacts are the subject's own, the cited
claims pass the audit; review names problems back to the writer once at most).
The claim audit judges only lines the run wrote; carried lines are recorded, not refused.
A model turn that times out is retried once in the same thread when available, and usage from the failed attempt is counted.

```bash
co rem enrich projects/aurora.md   # discovery: follow what the page has not followed
co rem muse projects/aurora.md     # thinking: ask, choose, study, write only on insight
```

- **enrich** reads the page, its cited originals and a reading ledger: every
  source the saved mail archive and coding sessions hold about the subject,
  laid out as searchable files with an index, and which of them the page
  already cites. The model follows links (it may open them on the web),
  unread attachments, names, older threads and other channels, adds what they
  establish, and replies with a lead list: `followed`, `open` (the next run's
  work) and `blocked`. The lead list is printed and kept in the run record.
  Project history is studied oldest first, one period per turn in the same
  thread before other leads, with the full GitHub listing up to 5,000 issues
  and 5,000 pull requests per repository. For each period's most important
  decision, it quotes your own words exactly, in their original language,
  from a session message or mail you wrote and cites it; if none exists,
  it says so in its reply.
- **muse** is one conversation of seven turns in the same Codex or Claude Code
  thread (`co ai --json --resume <session>`): turn 1 writes at least twenty
  questions and picks five; turns 2–6 study one question each and edit the
  page only when the answer is an insight that needed two or more sources;
  the last turn looks back, brings the lead and the page's shape in line with
  what changed, and lists the questions left open. Its material is the page,
  its cited originals, and the latest enrich lead list and muse open questions
  for that page.

Before muse saves the page, an independent reviewer checks each proposed new
Insight bullet against its cited originals and the existing page, without seeing the writer's reasoning.
Only good insights are kept; weak or wrong bullets are removed, and a weak finding about an obligation
or a question still owed can move to Open threads.

Both send dropped `“…”` quotes or pre-existing `Sources` ids back for repair;
if one repair cannot restore them, the lost lines are put back as they were,
with citations renumbered, so the page keeps its new work. A quote the page
had that is not in its cited source is not guarded.

Both print whether the page changed and its size before and after, record a
run in `co rem logs` (with usage, counted in the separate deepening budget),
and change no other page. They work on people, projects and orgs
pages.

### Deepen over time: co rem deepen

```bash
co rem deepen             # one slot: three pages by default
co rem deepen --pages 1
co rem deepen projects/lantern-skills.md avery-lin
```

Optional `PAGE...` selectors resolve like enrich/muse and deepen only those
pages once, starting in the given order and checking the budget before each page; `--pages`
limits automatic selection only.
`limits.depth_workers` (default 3) controls how many pages deepen at once, including explicit `PAGE...` selections.

One round on one page is **enrich, then muse**; large-page rounds measured on
2026-10-20 took 35–97 minutes, mostly waiting on model turns. Round N reads
round N-1's open leads and open questions through the latest completed run
reports. Muse still runs when enrich fails or is refused, using what is there.
Automatic selection skips a page for 24 hours when its latest enrich or muse outcome reports a timeout, a provider at capacity, a turn that did not complete or a runner that could not start; explicit `PAGE...` selections still run.

Candidates include every notebook page under `people/`, `projects/` and `orgs/`, excluding
the owner and mapped automated accounts; map rows supply activity, while unmapped
projects use Sessions under Paths (0 if absent) and Last seen. Orgs sum their
mapped people's mails and use those people's newest Last seen; unmapped people
and orgs have value 0.
Mapped orgs with no people, or only automated or one-way people, are excluded.
The highest priority goes first, ties by record:

```text
priority = log2(2 + value) ** 2 * recent * thin / (1 + rounds)
value = mails for people, sessions for projects, its people's mails for orgs
recent = 2 for activity within 30 days, otherwise 1
thin = 1 / (1 + quotes/3 + sources/10)
```

Quotes and sources count distinct entries on the current page. A page rests
for 30 days when its last round changed neither characters, quotes nor sources
and found no insights, or when each of its last two rounds gained little:
`gain = (quotes after - before) + (sources after - before) + insights` is at most 1
and the absolute character change is less than 600 in each round. Rest starts
at the last round. Each round appends its metrics, outcomes, lost quotes,
insights and token-based points to `.state/depth.json`, keyed by record.

`limits.depth_quota_points` defaults to **30 points of the Codex week**,
separate from investigation's 35; `limits.depth_pages_per_slot` defaults to 3.
The shared `limits.quota_floor_percent` (90) also stops new pages. Both bounds
are checked before each page. Usage counts enrich and muse run logs within
the reported quota window, or the last seven days when the meter is unknown.
`limits.depth_slot_minutes` (default 60) stops new pages once elapsed slot time
reaches it, including explicit `PAGE...` selections; started rounds finish.
Each picked page gets a line with its value, recent multiplier, quotes, sources
and next round number. `--json` includes these selection metrics and priority
under `picked` (`rounds` is the number of previous rounds); results under `rounds`
are in completion order.
The round table shows before/after characters, quotes and sources, insights,
lost quotes, both outcomes and points; it also reports why it stopped and how
many candidates remain.

Scheduled `co rem sync --scheduled` runs a slot after a due daily round,
unless that round was partial. Manual `co rem sync` never deepens pages.

### What the reader shows

The reader returns the context REM carried forward, then helps you recall an
older page before showing its answer. It remains a point-in-time snapshot.
When pages already exist but no background schedule is authorized, its status
says **Background updates off** and offers `co rem start`; the written pages
remain available. A wholly empty notebook still says **Not started**.
Status, theme and privacy controls live in the sidebar’s **Reader settings**
disclosure. **EN | 中文** beside the theme controls switches interface labels
and dates. Your saved choice comes first; otherwise Chinese is preferred when
it is among your languages, then a Chinese browser language, then English.
Older notebooks without saved language detection read your own sent mail and
typed sessions on opening, without writing to the notebook. Configured
languages still take precedence. Page prose stays as written. On phones, a compact brand and search header keeps Browse within reach.

- **Home** is a morning brief, read top to bottom. A date line and one
  sentence count what matters ("1 change overnight · 1 due soon · 4 waiting
  on you"); a quiet line under it summarises the last pass, with its
  hypnogram one click away in **How co rem processed the last pass**.
  **Overnight** lists only verified field changes from the run log (old and
  new value, with a link to the source). In 中文 mode the new value comes
  from the page's cached translation when it matches; a value with no
  translation is shown as written with a small 原文 mark. A page rewrite
  alone is not a change, and a quiet night says so. **Today** lists open threads, in either
  direction, that are overdue, due within three days, or new today.
  **Open threads** shows the three most important things waiting on you that
  Today did not already show. **Find** is a search field with task entry
  points (who do I owe, what changed this week, people, projects,
  everything). **Worth remembering** and **Gone quiet** sit beside the brief on
  desktop. **Pages rewritten this week** stays collapsed. The owner's page is
  pinned as **You**.
- **Thread actions**: every open thread on Home and in Open threads has
  **Copy prompt** and **Mark done**. Copy prompt puts a ready-to-paste prompt
  for Codex or Claude Code on the clipboard. It contains the thread, its page
  with the `co rem show` command, other pages carrying the same thread, and
  the cited source ids and dates, and it asks the agent to draft without
  sending anything. Labelled private passages are left out. Mark done hides
  the thread from Home and the counts in this browser only (local storage,
  per notebook); with storage blocked it lasts for the session. **Undo** is
  offered at once and under **Marked done on this device** in Open threads.
  Nothing is sent and the notebook is not changed; the next pass that sees
  your reply closes the thread there.
- **Merged threads**: the same request copied onto several pages is shown
  once, with **Also on** naming the other pages. Copies merge when they cite
  the same message and one mostly repeats the other's distinctive words, or
  when dated within a week with matching wording. Written dates such as "23
  October 2026" or "Sep 3" count as dates. A page's undirected line can join
  a directed copy of the same request; two different requests in one email
  stay separate.
- **People, Organisations and Projects** open as a sheet: one row per page,
  the facts in columns (People starts with name and summary, what's open,
  company and last contact, each one line with the full text on hover; **More columns** reveals role, email, phone and
  mails, remembering your choice in this browser; status is the moon beside
  the name), a sticky header, sort on any shown column, filters (*Something open*,
  *Yours to answer*, *Written*, *Mapped only*) and a text filter. A row opens
  the page. It fits 1440 px; narrower, it scrolls inside itself with the cut
  edge shaded and the name column held. On phones, People become cards with
  contact details and open work; empty columns are omitted on desktop. The columns come from the notebook's
  index (`store.people_table`, #2067) when `.state/rem.db` exists, embedded in
  the snapshot; before it does, from each page's Facts and the map's mail
  counts (`index_rows` and `mail_facts` in `reader.py`, `facts()` in the page).
- **"You", not "the user"**: pages are written about "the user"; the reader
  says "you" ("you have not signed it", "How you write to them") at render
  time only, so the Markdown and Copy Markdown keep the words as written.
- **Memory markers**: a dawn dot means **updated last night**, for pages
  rewritten in the latest pass. A faint underline marks a recorded field
  change, with before/after values on hover. A hollow circle beside a citation
  means the sentence explicitly says its claim is unconfirmed; uncited prose
  gets no marker. On entering a page, these update markers fade in once and the
  changed-field underline draws in about 600 ms. Filtering or rerendering the
  same view does not replay them; reduced motion shows the final state immediately.
  A short legend lives in **Reader settings**.
- **Between you** on a person's page lists what you owe and what they owe in
  two quiet columns; each thread's age sits at its top right, amber for what
  you owe, as on Home. Project and organisation pages show each date once,
  under the title, in the reader's date format; when the file was last
  updated is noted in the Full memory and sources header. In 中文 mode,
  Facts values and Related pages snippets come from cached translations
  when they exist, and otherwise show the original with a 原文 mark.
- **A page** opens on a focused status, next exchanges, compact facts, related
  records and filterable dated Activity. Project pages add purpose and a
  recorded decision when supported. A project opens on its current supported
  finding; on a phone, a long purpose shows four lines with **Read full purpose**
  (**展开用途**) to reveal the rest in one tap. Its citations stay directly after
  the purpose and its toggle. Connected cards without a snippet stay compact;
  desktop cards with snippets align their source dates across each row.
  When only part of its queued or archived session history was read,
  the page says how many inputs were supplied. Explicit links and unambiguous name
  mentions make cross-page cards and backlinks; their labels distinguish a
  link from a mention. The original prose, every Facts/Contact field,
  Insight, History and Sources stay under the always-visible **Full memory and
  sources** disclosure; decision pages also start with it collapsed. A claim
  number `[n]` opens its source description and, when locally archived, an
  original excerpt. Prose uses quiet raised date markers, kept beside the
  preceding word; hover or focus reveals the full source label. Adjacent
  citations share a marker. The source panel keeps the claim and available
  sender, channel, date and subject visible while excerpts are hidden; **Show
  labelled passages** reveals them using the existing privacy setting.
  Grouped citations keep the page compact; each numbered
  row under Sources can also open its own original on a phone. An accepted
  explicit investigation retains the live coding-session inputs it cites,
  even when they were absent from the older map. Cited mail bodies show up to
  4,096 characters, retained coding inputs up to 4,096, and repository
  snapshots up to 65,536, with truncation
  marked. Cited conversations show up to twelve recent archived
  messages with the total count. Excerpts labelled `[personal]` or
  `[sensitive]` appear only in the reader on this computer (the snapshot and
  the local live reader), behind **Hide labelled passages**; the O Chat view
  never receives them and starts with labelled passages hidden. Missing original bodies are labeled, never
  replaced by a generated summary. A page only mapped from metadata says so
  and gives the command to investigate it.
- **Open threads** shows all supported obligations with direct record links.
  Within each direction section, rows keep their date without repeating the
  direction tag. **Memory changes** keeps cited field changes separate from
  page rewrites.
  Older run logs have no claim-level comparison; they show an empty state.
- **Search** routes common requests such as “who do I owe?”, “what changed?”
  and “connected to Mara Ostrowski” to task views. Literal search also answers
  first: when a person's or organisation's name matches,
  a *Best match* card gives the email, phone, last contact and what is open.
  The rest is grouped by kind, people first, one snippet a page, never a
  local path.

Design: cool blue-biased neutrals with one night blue for links and one lamp
amber kept for what is owed; a dark palette of its own; Optima for titles,
Charter for prose, the system face for chrome and the mono face for every
date, count and id. Fonts are local faces, so the page makes no network
request. Every view fits a 390 px phone without sideways scrolling, keyboard
focus is visible, and the hypnogram line is visible immediately. Quotes use a
warm tint in light mode and warm text with a faint underline in dark mode;
search matches keep their distinct highlight. Motion respects `prefers-reduced-motion`.

To see every view on an invented notebook, light and dark, desktop and phone:
`python scripts/capture_rem_reader.py OUT_DIR` (the fixture is
`tests/fixtures/rem_reader_notebook.py`; `--root COPY` renders a copy of a
real notebook, and those screenshots stay local).

`init` is the foreground Skill workflow and offers the background schedule at
the end. `start` remains the explicit command to resume or change that schedule.
Map is a stage inside rem-init, not a separate model runner.

Map reads known information before leaving basic fields unknown. It uses the
single person-page definition; investigation reads that same existing page,
keeps supported facts and fills gaps. The owner is investigated first.
Automated notices are signals for the Skill to classify, not an automatic
rule to discard companies or event opportunities.

## Choose a harness

```bash
co rem config set runner codex model gpt-5.6-luna
co rem config set runner claude-code model default
co rem config set runner coai model co/gemini-3.8-flash
co rem config set runner coai model ollama/qwen3
```

A model name must be available in the selected provider/account. `default`
omits the model flag. Changing runner without a model chooses that harness's
default. Old coai configs which retained the unused Codex default migrate to
their previous effective behavior (COAI's default). No credential belongs in
co rem configuration.

### The job's shape: agent or summary tier

Not every model can drive tools, and model names change under us, so the
shape of an investigation is measured rather than read off the name (#1847).
Changing `model` or `runner` runs a capability check: one investigation of a
built-in fixture page (two mails, in a throwaway notebook; none of your data)
through the configured runner, graded by code — the page must state the
fixture's fact and cite a fixture message. The result is recorded in
`.state/tier.json` with the runner, model and time it was checked for.

| Tier | Who gathers | Who writes the page |
|---|---|---|
| `agent` | co rem's code gathers; the harness reads the material with its file tools | The model writes the page file itself, as the investigate Skill says |
| `summary` | co rem's code gathers everything, including a project's files, and hands it all over inline (digested first if it does not fit) | The model replies with the page, one page per call; the reply becomes the candidate |

The agent tier is tried first; a model that fails it but fills the page by
reply is the summary tier; a model that does neither is not recorded and the
command fails with a `Next:` line. `co rem config` shows the tier in force.
A notebook never checked, or checked for another runner or model, runs as the
agent tier (the behaviour before the check existed) and `co rem config`
says so and names the command that checks it. `--no-check` saves a new model
without checking it.

```bash
co rem config set model gpt-6-luna      # saves, checks, records the tier
co rem config                           # Tier: in force, checked, when
```

Equivalent direct CLI delegation, useful in a shell script:

```bash
co ai --json --harness codex --model gpt-5.6-luna \
  "/rem-investigate Update /path/to/rem/people/alice.md; read its current content first."
```

The direct Skill call does not run co rem's deterministic source collection or
advance its sync cursor. Use `co rem investigate` for that orchestration.
COAI expands the Skill name and supplies its installed directory.

Every co rem model turn starts from the fixed `.state/tasks/` workspace inside
the selected co rem root (`~/.co/rem` by default). Codex therefore groups
those turns under one workspace in its history. Inputs, review results and
disposable page copies live in per-run subdirectories there;
the runner validates a candidate before promoting it to the notebook.

Every co rem stage reads text other people wrote -- mail bodies and PDF, DOCX
and XLSX attachments -- and the daily job `co rem start` installs runs with
nobody watching. So every stage, scheduled or started by hand, runs confined:

| Runner | Flags co rem passes to `co ai` | What the model can do |
|---|---|---|
| `codex` | `--sandbox workspace-write` | Read files; write only inside `.state/tasks/` and TMPDIR; no network |
| `claude-code` | `--permission-mode acceptEdits` | Read and write inside `.state/tasks/`; commands, web fetch/search and reads elsewhere are denied, since nobody is there to approve them |

`co rem start` shows the row for the configured runner in its consent
summary, as `model_permissions`, before you approve the schedule, and
`model_receives` names whose login the model is called through (Codex or
Claude Code). Change the runner later and the next `start` shows the
summary again.

Model turns and the launchd job both run the installation that is running
`co rem` -- `<its python> -m connectonion.cli.main` -- not the first `co` on
PATH. Starting from a non-activated venv with an older `co` in `~/.local/bin`
used to install a job, and route every model turn, through the older one.

co rem's own code fetches the mail and attachments before the model starts, so
the model needs nothing more than to read that material and write the page
copy it is given. The cost is the web: investigation no longer looks up a
role or a switchboard number with `co browser`, and says so in the page's
`Uncertainties`. Before 1.8.8 investigation ran Codex with
`danger-full-access` and Claude with `bypassPermissions`, which gave anyone
who could email the user an unattended agent with a shell, the network and
the user's mailbox; a line in the prompt was the only defence.

co rem removes an ambient `ANTHROPIC_API_KEY` from Claude's subprocess
environment so the run uses the selected account's subscription rather than
silently billing the API. Skills govern what the task should do; they are not
OS permission enforcement.
The removed scoped rem_* tools are no longer a filesystem guarantee.

## Source coverage and output

Gmail/Outlook programmatic collection searches the requested date windows.
Sync lists each weekly window 200 messages at a time and splits any window
that comes back full until every half fits, so a busy week is read whole; a
single second holding more than 200 messages stops the scan with an error
rather than skipping them. Investigating a person on a client without a
server-side search still reads at most 200 messages per weekly window.
Coding investigation now walks successive batches until the cursor stops,
rather than stopping at 40 messages. It searches aliases and project paths;
an owner identified by mailbox address receives their own typed session
messages. Injected Skill prompts are not reingested as user experience.
The importer still labels oversized pasted session text as truncated.

A prompt a program sent is not the user's: a Claude Code row with an `sdk`
entrypoint or an `sdk`/`system` prompt source is skipped. A launchd job's
scheduling prompt had become the user's request on projects/layeredvisions; on
the owner's machine 1,437 of 1,454 sessions opened that way were schedulers,
harnesses and REM's own turns. Claude Code project discovery reads forward to
the first record with a `cwd` (at most 256 records or one megabyte), because a
session can open with queue, mode or bridge records (#2336).

The first investigation saves the parsed, typed coding messages it scanned in
the notebook's private `.state/session-windows/` directory. Later CLI runs
check the local session files and read only changed files, then select messages
within the requested page window. The cache contains message text and source
IDs, but not whole tool-output transcripts. It is not included in reader
exports. Deleting that directory forces the next investigation to rebuild it.

A session REM does not read, such as one of REM's own turns or a program's
prompt, is recorded as skipped the first time it is seen and is never opened
again, even while it grows. On the owner's machine 11,473 of 15,000 Codex
rollouts were REM's own turns. Every scan reopened them, and a warm scan took
80 seconds; it now takes about 6. A cache from before Codex `exec` sessions
were excluded is migrated in place: only the items from such sessions are
dropped, and nothing is read again. Within one run, the mail metadata and the
project notes that every page searches are parsed once and then reused until a
file changes.
Before page workers start, init and `co rem investigate CATEGORY` scan the
session stores once, so no page waits on that scan or counts it as its own
gathering. A person's search of the project notes first checks each note for
the name in one pass and excerpts only the notes that contain it.

What counts as a message you typed to Codex (#1978). Codex Desktop puts every
message in the user slot under a metadata block, typed or injected, and says
in `content_item_kinds` what each part is. A message whose parts are all
`user.*` (text, an image) is yours and is read; one that names anything else
(`agents_md.instructions`, `environments.environment_context`,
`plugins.recommendations`, `goal.internal_context`, a selected skill), or no
kinds at all, is the client talking and is skipped and counted. A message that
opens with a harness tag is still skipped, except the in-app browser context
Desktop puts in front of what you typed: that block is dropped and your words
are kept. Two kinds of thread are not read as yours: a subagent's (the
approval reviewer, a spawned worker), whose user slot the agent wrote; and the
history of a Claude Code session imported into Desktop, which co rem already
reads from Claude Code itself. What you type after an import is read. The Codex
CLI's plain three-key message is read as before. `$skill-name` counts in a
skill page's Usage history use the same reading.

PDF, DOCX, XLSX, PPTX (including tables/notes), plain text, HTML and ICS
attachments are read; XLSX needs `pip install 'connectonion[rem]'`, and
without it a spreadsheet is named as unread with that command. Investigation passes full extracted text to chronological
digest chunks instead of dropping a long attachment's tail. Unreadable
formats/errors remain visible. The Skill supplements from the account's
`co email` service, known documents and public sites, and reports what it
could not search. Own-mail sent history currently has no paginated CLI;
Jira discovery/auth is not connected to this co rem entry point yet.

Each task supplies material and composed instructions as files, avoiding
OS argv size limits. File changes are observed on disk, including deletions
and partial changes on failure; a success sentence is not a file-change count.
Extraction returns its written notes file, not a commentary/status reply.
Nonzero exits, missing/malformed envelopes, provider errors and timeouts fail
the task. Investigation is not marked finished on a failed execution.

co rem forwards its delegated deadline as `co ai --timeout SECONDS` and gives
the outer process 15 seconds to exit afterward. The common native adapter
therefore closes its delegate before co rem process timeout is reached.

## Scheduling and accounting

In opt-in preview **1.9.3rc21**, Codex notebooks default to **Codex desktop Scheduled** when the app
is installed and the notebook timezone matches this computer. The desktop
adopts a private local automation definition; there is no public App Server
schedule RPC in the tested version. Keep the app open and computer awake.
Completed native wrapper conversations and REM's internal Codex calls are
archived, retaining their trace IDs without filling active project history.

`co rem start` stages a paused task and verifies native index adoption before
removing an old launchd clock. A running old batch or failed registration leaves
the previous clock intact. Run start again after that batch finishes or Codex
initializes. `status` distinguishes registration, first execution, a stopped app,
an overdue trigger and a failed REM pass; a file alone is not a working schedule.
`stop` pauses the native task and retains its history. It does not cancel a native
model turn already in progress.

The native adapter in rc21 uses Codex's legacy local-file registration. Newer
desktop code also has account-managed registration, which can replace the local
file and task ID. That registration route has not passed REM's live acceptance;
the presence of a TOML parser or an enabled feature is not proof of compatibility.
The normal-profile follow-up on 2026-10-24 registered a task but did not observe
its timed execution; an unlocked, visible-window comparison is still pending.
Check `co rem status` before relying on unattended upkeep;
`co rem sync` remains available by hand.

**Under review, not yet released:** initialization opens the normal installed
desktop when it is not running, then independently confirms activation. Stopping
waits for native pause acknowledgement before marking the worker disabled or
starting a replacement launchd timer. A known account-migrated task is identified
by its legacy association and requires management in Codex Scheduled until an
authoritative account registration API has been verified. REM does not recreate
its old file or treat a cached account status as confirmation of a pause.

Other runners, headless Macs and saved timezones different from the desktop retain
launchd. Its five-minute tick keeps the saved timezone and coalesces missed slots.
The native desktop uses its own local wall clock and startup/missed-run behavior;
REM coalesces overdue saved slots when the next native trigger reaches the CLI.
Exact time pairs use one rule with position selection, avoiding extra combinations.
Spring DST gaps move forward by the gap; a repeated hour is served once, at its
first occurrence. Moving the computer to another timezone needs `co rem start`
to select the matching scheduler. No REM timer daemon is added.

The job imports the checkout that ran `co rem start` when that is a source
checkout, and nothing for an installed package; it never copies the shell's
`PYTHONPATH`. The live job carried a scratch folder from an old session, which
would have shadowed the installed package on every tick had it held a
`connectonion/__init__.py`.

Each notebook root is its own job, `ai.openonion.co-rem.<hash of the root>`,
the default `~/.co/rem` included, so `co rem start`/`stop` under another
`HOME` never touches your real job. A job installed before 1.8.8b12 under
the bare label `ai.openonion.co-rem` is still found: `stop` removes it and
`start` replaces it, but only when its own `--root` is this notebook.

Sync retains its source cursor on failure. Two-stage batches reserve two
attempts and cannot start with only one remaining; extraction usage survives
a later maintenance failure. Reported tokens are not account quota or dollars.
The input-character limit bounds gathered/digested material, not every tool
read a delegated agent may perform.

### Codex quota (#1843)

With the Codex runner, the notebook reads your Codex plan's own meter: the
weekly window's `used_percent`, its length and when it resets, as
`codex app-server` reports them (`account/rateLimits/read`). Reading it starts
no model turn and costs nothing. Codex reports whole percents, so every figure
below is good to about one point.

- **Every run records the meter before and after** (`quota` in the run log,
  shown by `co rem logs`). The difference is what that run cost in points of
  your week, measured rather than estimated from tokens.
- **Runs that overlap share one meter reading.** Init and CATEGORY runs write
  many pages at once, and each page's before/after spans every other page's
  spend. Summing them counted the same movement up to sixteen times: on real
  first runs the meter moved 3-10 points while the per-run sum said 75-154. Runs
  whose times overlap are now one group, and a group costs what the meter moved
  from its first reading to its last. Gaps between groups are not counted, so
  your own coding between runs stays yours.
- **A group the meter cannot see is counted from its tokens** (#1990). Codex
  reports whole percents, so a small group can read the same before and after.
  It then counts `(input − cached input + output)` divided by 12,000,000 at
  standard speed or 6,000,000 at fast speed (fast bills twice). Seven large
  first runs at standard speed moved the meter one point per 11.6M-13.6M fresh
  tokens. This fallback only applies when the meter stayed flat, so its error
  is under one point per group.
- **Scheduled investigation has a weekly budget**, `limits.investigation_quota_points`,
  default **35** points of the weekly window. The
  scheduled round adds up the points its investigation runs used since the
  window last reset, and starts no new page once that reaches the budget.
- **The initial investigation has no REM quota gate.** It attempts the whole
  selected cohort, even when the weekly meter passes the routine budget or
  safety floor. The runner provider can still enforce its own account limit.
  Claude Code and other runners without a readable weekly meter show an
  estimate; the CLI cannot claim to have measured their plan usage.
- **Manual investigation is metered too** (#1842). `co rem investigate PAGE`,
  `me` and CATEGORY runs record usage. A CATEGORY run covers all pending pages
  by default, using `limits.workers` (default 16), as init does. Set it with
  `co rem config set limits.workers 8`; `--workers N` overrides one run (1–32).
  `--limit N` or `--budget N` alone uses one worker.
  It stops starting pages when its explicit `--budget N` is spent or at the
  safety floor. Pages already in flight finish.
- **After init**, `co rem investigate all --budget 10` works whatever init left:
  one queue over people, projects and organisations by weight (the same order
  the round uses), until 10 points of the week are spent. `--list` shows that
  order without running a model.
- **A floor protects your own coding during routine and manual runs.** These
  start no new investigation page once the week is at
  `limits.quota_floor_percent` or more, default **90%**. Init is the exception.
- `co rem status` reads the meter now and says it in two lines, for example
  `Codex week: 5% used on pro; resets Sun 04 Oct 09:49` and
  `Investigation this week: 0 of 35 points; nothing starts once the week is at 90%`.
  The dashboard says what a point is under the line.
  `--json` gives the same numbers under `quota` and `investigation_quota`.
- When the meter cannot be read (another runner, Codex not signed in, an older
  Codex), the run says `quota: unknown (<why>)` and the daily call cap
  (`limits.runner_calls_per_day`) is the only bound, as before.

Maintenance is not quota-gated: it is the incremental daily pass and stays
bounded by the call cap. Its cost now shows in points, so a cap can follow
from real numbers. This supersedes the earlier unimplemented 2% initialization
/ 1% daily targets, which needed exactly this meter.

The scheduled daily round maintains first. It saves detected owner languages after
maintenance, including a partial maintenance result, before deciding whether to
investigate. The first run of the local day then
investigates unfinished pages, most recent activity first, within a reserved
share of the daily attempt cap (8 calls; a person is one investigation); every later run
updates only the people with new mail and the projects with new messages since
the run before, at most 5 pages. Both stop at the weekly budget or the floor and
record how many pages are left ([details](rem-people-pages.md#the-daily-round-four-runs-two-jobs-1723)). Initialization maps sources first, then runs a model investigation of the selected pages; manual
investigation remains outside the scheduled cap.

The UI is a static snapshot of the notebook as it is now; run `open` again to see later changes (`--no-launch` says so and ends on `co rem open`). No merge,
release, new background job, broad mailbox backfill or production co rem rewrite
is implied by the architecture refactor.

### Investigate an installed skill

```bash
co rem --root /path/to/rem investigate skills/catalog/example.md --eval-dir /path/to/.co/evals
```

Skill pages first collect local run evidence, then use the configured runner
to write a cited page from the installed source instructions and those records.
The skill is never executed merely to document it, and mail is not read. Omit `--eval-dir` to use `~/.co/evals`; repeat it for
additional summary directories. The collector reads immediate summary YAML files
(up to 1,000 per directory, 4 MB each), matches exact `/skill-name` inputs, and
deduplicates retained run/turn identities. It writes a linked note containing
inputs, retained outputs, reported tool calls, recorded evaluations and coverage.
The skill page gets a managed `Run evidence` block and an `Insight` describing
a concrete use, mismatch or limitation that changes the reader's next action.
The map-owned source provenance is preserved. The investigation stamp records
that the page was reviewed; it does not certify execution success. Without
reviewed artifacts, reliability remains unverified. Unsupported optional
sections are omitted after investigation.

Counts describe retained evaluation attempts, not proven starts or lifetime runs.
Tool-invoked skills and other harnesses are not yet covered. Historical outputs
may be missing, current summary model labels may not establish each run's model,
and same-name installed copies cannot be attributed. Goal achievement and
verified changes stay unassessed until actual artifacts are checked.

### 1.8.7 integration update

`co rem --root '<root>' init --days 150` first builds people, projects and installed
skill maps deterministically. That map phase invokes no model. Current init then
investigates the owner and selected pages, recent first; see Start here.
Only enabled mail sources are read. Use `subscriptions` and explicit `subscribe`
commands to select sources first. The map records counts, dates and coverage in
`.state/map.json` and writes people/project indexes under `notes/`; it leaves
classification unassessed. The `rem-init` Skill runs init and checks its result.
Use `investigate <record>` to revisit or retry one page.

Investigation reads a normalized skeleton and writes a new candidate under
`.state/tasks/`. Only a candidate with valid structure and reference definitions
replaces the page. Failed candidates remain for diagnosis. This check cannot
establish factual correctness. Full source JSON is retained; a readable copy uses
reversible text chunks so line-limited tools can read all of it.

The requirement-to-code/test checklist and remaining decisions are in
[rem-187-checklist.md](rem-187-checklist.md). This historical note covered the
map stage; the current first run also investigates the owner, eligible
people, projects, related organizations and installed skills.

### First-run People and installed Skills

`co rem init` runs without questions in terminals and scripts. It uses connected
mailboxes automatically and prints `co auth google` / `co auth microsoft` tips for
disconnected sources after building the local maps. Authenticate and rerun init
to add People. To restrict mapping to a specific mailbox:

```sh
co rem init --mail outlook
# or: co rem init --mail gmail
co rem init --days 5       # small first-run trial
co rem init --all-history --investigate-all --estimate-only  # historical census and cost preview
co rem open
```

This lists 180 days of mail by default: correspondent metadata plus the short
preview the provider lists with each message. A seven-day window that fills the
provider's 200-message listing cap is split until every message in it is
listed, so a busy week is no longer cut off at 200 without a word. Init offers
the schedule after its first run and subscribes the mailboxes it read. Nothing
is read in the background until that source and schedule summary is approved.

The historical census may take several minutes and can be a lower bound when
one mailbox is unavailable. The status and private source inventory name every
failed mailbox or time window. A contact seen only once remains findable in the
reader's unreviewed directory without creating an empty person page.

#### Private mail materials

After the map, init saves each listed message body once, so investigating a
person later reads the saved window from disk and only asks the mailbox about
mail outside it. Everything lives under the notebook's `.state/`, which is
owner-only (`0700` directories, `0600` files) and never shown to a model as a
page or sent anywhere:

| File | Holds |
|---|---|
| `.state/source-inventory.md` / `.jsonl` | What was listed, window by window: ids, dates, senders, recipients, subjects, session paths. No bodies, no previews |
| `.state/mail/messages/<provider>/<hash>.json` | One provider-rendered text body per message. Attachments are not downloaded |
| `.state/mail/people/<hash>.jsonl` | Each person page's messages, by reference; a mail to three people is stored once and indexed three times |
| `.state/mail/projects/<hash>.jsonl` | Each project page's local session files, by reference |
| `.state/mail/archive.json`, `summary.md` | Range, counts saved / reused / failed, and status |

Pages never contain a raw body. A body that could not be fetched marks init
`partial` with a nonzero exit; rerunning reuses every saved body and fetches
only the rest. If a later init cannot list a mailbox, the earlier archive is kept
rather than replaced. `--no-mail-archive` skips the body download and keeps the
metadata-only map. Investigating a person or an organisation reads whatever
part of the archive is saved, even while it is still being saved (#2042): the
mailbox is still listed for the window, but a message whose body is on disk is
not fetched again, and coverage says how much of the archive there is
(`12 loaded from private init archive (2,693 of 3,152 bodies saved so far)`).
The per-person indexes are written whenever the archive pauses, not only when
it finishes. A sync that resumes the archive says so, with its progress:
`Saving mail bodies: 1,200 of 3,152`.

A person is named, in this order, by the name they write under, the name in the
owner's saved contacts (Google contacts and "other contacts", Outlook contacts;
skipped when the login cannot read them), and the owner's own greeting in a mail
to that one person ("Hi Fenwick,", "Fenwick 你好，", "子亚，"). A greeting to several
people names none of them. On the owner's notebook this named 176 of 195 people
the map had titled with a bare address. An organisation is the registrable
domain (accounts.google.com and google.com are one), and a domain only notice
senders write from gets no page. A page still titled by a bare address whose
sender the owner never wrote to is held for review: kept, but left out of the
investigation queue, `co rem list` and the reader's contents. `co rem list
people --review` shows them; a later init that finds a name or a reply from the
owner, or investigating one by its path, brings it back. A nameless address the
owner has written to, the agent's own included, stays an ordinary page, and an
investigated page is never held -- except one the owner only ever writes to and
never hears from, the shape of their own other mailbox: it is held too, and
still asked about with `init --mine` (#1987). A sender whose display name is its
own domain ("Airbnb" <discover@airbnb.com>, "Google Cloud" <googlecloud@google.com>,
"X" <notify@x.com>) and who writes at least three times as often as the owner
answers is a service: listed with the notice senders, no people page, and an
older map's page for it that holds only map output is archived. Someone writing
from their own name at a domain named after them (aaron@aaron.dev) stays a person.
Skills and projects are one page per skill name and per repository (below). With `--mail`, only explicitly selected
mailboxes are read. Missing or failed sources appear in the mapping coverage;
without a selected mailbox the command explains why People is empty.
The terminal shows one line per mapping stage, a short count of People,
Organizations, Projects and Skills, and your own page's facts. Full per-source details stay in `.state/map.json` under the
co rem root and in `--json` output. A custom `--days` window is preserved in the
printed next command and retry tips.

Skills lists one catalog page per name; the page lists each installed copy and
says which differ. The generated index is not counted as another skill.

#### One page per repository

A project is its repository, not each folder a session ran in (#1974). A git
worktree folds into its main checkout's page:

- a folder whose `.git` is a file saying `gitdir: <repo>/.git/worktrees/<name>`
  belongs to `<repo>`;
- a folder under `<repo>/.claude/worktrees/` belongs to `<repo>`, even after
  Claude Code removed it;
- a folder under `.worktree/` or `.worktrees/` that no longer exists belongs to
  the repository beside it whose folder name starts its own
  (`~/projects/.worktree/browser-139` → `~/projects/browser`); with no such
  repository it is left out rather than guessed.

`Paths` lists the repository root and a count, not the worktrees:

```text
## One count for every screen (#2008)

The reader said "174 with findings" when three pages had been written: a mapped
skill page shows its description and a mapped project page its paths, and both
read as findings. People were 76 on one screen and 82 on another, skills 159 and
152. Now `connectonion/rem/census.py` is the only place that decides, and the
reader and `co rem status` both ask it:

- **Counted**: people, projects, organisations and skill catalog pages. Not
  counted: pages held for review (no name, never written to), services and
  automated senders that still have a people page, and the skills index.
- **Written**: a page someone or a model wrote — its status line no longer says
  "not investigated yet". A merge keeps the investigated page's status, so a
  merged page counts exactly when what it kept was written. A mapped page with a
  description or paths is not written.
- **Last activity**: the page's own date — the last contact of a person, the
  last session of a project, the date of its last investigation — never the
  file's modification time, which is when the last map rewrote it. "Recently
  active" in the reader lists written pages by it and shows it.

## Facts and Insight on every page (#2068)

The owner, many times: an investigation finds too few facts and too little
insight, and on Corin's page the phone number could not be found at a glance. A
page now opens on a **Facts** block — one field a line, each value cited, a
missing value visibly `Unknown` — and a short **Insight** section; the prose
sections follow. `connectonion/rem/facts.py` owns the shape; the reader renders
the block as a card.

### The data shape (what the reader reads)

```markdown
## Facts
- Email: mia.chen@harbour.example
- Phone: +61 2 5550 0142 (work) [1]; +61 400 555 019 (mobile) [3]
- Company: [Harbour Analytics](../orgs/harbour-analytics.md) [1]
- Location: Unknown
```

- The section is `## Facts`. On a person page it comes straight after the lead;
  on a project page it is the first section; on an organisation page it follows
  `Domains`.
- One line a field: `- <Label>: <value>`. Every label of the page's kind is
  always present, in this order, spelled exactly:
  - **person**: Email, Phone, Company, Role, Location, Time zone, Links,
    How we know them, First contact, Last contact, Signing entity, Handles,
    Language, Also known as
  - **project**: Repository, Stack, Status, People, Organisation, Started,
    Last activity
  - **organisation**: What they do, Website, Location, Legal entity,
    Your contacts, First contact, Last contact
- An empty field is exactly `Unknown`.
- A field with several values separates them with `; `. Each value may end in
  a `(qualifier)` (`work`, `mobile`, `personal`) and then its citations
  `[n]`, which are numbers defined under `## Sources` like every other claim.
  A value may be a Markdown link.
- Dates (`First contact`, `Last contact`, `Started`, `Last activity`) are
  `YYYY-MM-DD`.
- `First contact` needs evidence of the relationship's beginning. The earliest
  retained message is an observed mail date, not automatically first contact;
  the Person writer and People index leave this fact Unknown when it cannot be
  established.
- Every value carries a citation, except `Email`, `Handles` and
  `Also known as`, which the map fills from the addresses it found. A citation
  at the end of a line covers the uncited values before it
  (`UNSW Founders; [UNSW](../orgs/unsw.md) [12]`); a full stop after it is
  ignored. A new value with no citation is taken off the page when it is
  saved (`review.json`: `facts_uncited_dropped`) rather than refusing the page.

`facts.parse(page)` returns `{"Phone": [{"value": "+61 2 5550 0142",
"qualifier": "work", "citations": ["1"]}, …], "Location": [], …}` (an empty
list is `Unknown`), so the reader and indexed views (#2067) use the same
parsed values where they display these fields. A page written before 1.9.0a9
has `## Contact` instead: `facts.upgrade` renames it and adds the missing
labels as `Unknown` the next time an investigation or maintenance writes the
page; `facts.parse`
reads either.

### Extracted before prose

Before the model turn, `connectonion/rem/fact_extract.py` reads the gathered
material with no model: the subject's own addresses, phone numbers in the
signature blocks they sign with their name (with `work` / `mobile` from the
line's label; not a number someone else is named beside), LinkedIn links, the
date of the last human mail between the user and them (not a newsletter, a
broadcast or a notice), the signature block itself,
the lines of calendar invitations that name the subject, and the company domain
when it is not a mailbox provider. They go to the turn as the
`investigation:facts` item, each with its source id, even when the rest of the
material is in files to search — the turn confirms them, extends them and
cites the source id, not the item.

Mail a relay or a system sends (Luma, Airbnb, no-reply), and a notice passed
on, gives no facts: the person's name sits over someone else's words there.

The model may correct a fact the material contradicts; it may not lose one.
After the turn, a phone, address, LinkedIn link or contact date the extractor
found that appears nowhere on the page is put back into its field with its
source (`review.json` lists it under `facts_restored`). Company and role from a
signature are context, not restored: reading a title off a signature is a
judgement.

A contact detail must be right or `Unknown`. On a person's page an `Email`
stays only if the person sends from it or is written to at it under their
name, and never a relay; a `Phone` stays only if a mail it cites was sent by the
person (or relayed under their name) with the number in it and nobody else
named to call beside it. What goes is listed under `contacts_unverified`. An
unknown `Company` is filled from the domain of the address they write from now,
never a mailbox provider, a relay, an agent address or a student address
(`company_from_domain` in `review.json`).

### Insight

A short section after `Facts` on person and project pages (the owner's own page
too, where it is the owner's month: what shipped, who is waiting): two to four cited bullets of what the inbox does not say outright, each
starting with its kind, which the reader shows as a badge —

- `- Now:` what this person or project is to the user's work today;
- `- Changed:` what moved recently (a new role, a stalled thread, a price);
- `- At stake:` what is at risk or owed, by whom, since when;
- `- Pattern:` something over time (replies within a day until August, then
  nothing; every mail is about invoices).

Generic lines ("a key stakeholder", "a valuable relationship") are not insight;
the benchmark refuses them. Thin material says `- Unknown`.

The lead above `Facts` carries the one line a reader opens the page for (#2065):
a person's states the balance — who owes whom what, and for how many days, or
`Nothing open as of <date>`; a project's says where the user stopped, what is
next and what blocks it. A claim is stated once in one clause; doubt goes once
in `Uncertainties`, and how the page was made (the mapper, the collector, how
many mails matched) goes nowhere in the body — that is the run's record.

### Fact coverage

`facts.coverage(page)` is the share of a page's fields that are filled; an
investigation's result carries `facts` — fields filled before and after, the
facts the extractor found and how many of them the page kept.

Measured on a copy of the owner's notebook (2026-10-02), fields filled of 14:
Corin 6, Greta 7, Emrys 6, the owner's own page 3. The material held more
than each page had: Corin's phone (in a signature), every page's first and last
contact, and on the owner's page a phone, links, company and role. After
re-investigating with these skills, Corin went to 8 (9 with the restore step over
the full window; the run was a quick pass of the newest mail) and Greta to 11,
her mobile among them, each with three labelled Insight lines.

When an investigation finds nothing new, the restore step still runs: a page
whose cited mail carries a phone the person signed with gets it back with no
model call. In a quick pass (`--quick`), the extractor sees only the sampled mail.

## Review before a page is saved (decision 079)

Every page a model writes — by `investigate`, `init`, the project writer or a
sync's one-page turn — passes the same review, and review settles what it can
before it refuses anything.

- **Quotes are checked.** A `“…”` on a person, organisation or project page
  must appear word for word in a source its line cites (line wraps, quoted
  reply markers and curly or full-width punctuation are ignored; `…` joins parts
  that appear in order). A quote whose original is not held, or is truncated,
  is left to the audit. On the 1.9.2b3 notebook 8 of 89 quotes failed: a fee
  quoted as “8% of gross revenue” where the owner wrote net, Chinese put into
  English inside quotation marks. Pages quote rather than retell the words a
  reader may act on (decision 076, originals over summaries).
- **Cited claims are audited** on every people, organisation and project page
  write, not only project investigations. The auditor reads the cited
  originals and the turn's own material, so mail the archive does not hold
  still counts. A packet over the bound is fitted by shortening every excerpt
  evenly instead of auditing nothing; a citation with no readable original is
  skipped, not a reason to stop. People and organisation pages add who-said-what
  rules: the sender of the cited message is who asked or approved, a cc is not
  a party, a passed event is not open, a contact detail must be the person's,
  and "not established" fails when a supplied original establishes it. Each
  finding names its failing claim. `INSUFFICIENT` is recorded, never a refusal.
  The auditor also reads the later messages in each cited thread, and the
  First and Last contact code computed from the whole archive: the packet's
  date range is not the relationship's. A claim a truncated excerpt neither
  supports nor contradicts is left out, not failed.
- **Up to two repair turns for every page type; one for enrich and muse.**
  What review names goes back to the writer with where to read the originals.
  Only project pages had repairs before; callum-reid and two skill pages
  stayed unwritten after 1.9.2b3's
  first run for one section or one citation. A page someone changed meanwhile
  gets no repair: it is theirs.
- **Last resort removes only what is refuted.** If, after the repairs, every
  remaining error is a citation, a misquote or an audit finding, the sentence
  holding each refuted claim goes (found without its `[n]` markers, since the
  audit copies claims without them), a contact field says `Unknown`, and the
  rest of the page is saved. `review.json` says `bounded citation audit failed;
  N refuted claims removed`. Anything else still refuses the page.
- **Code settles shape.** A heading glued to a paragraph goes back on its own
  line and a repeated section is merged into the first, instead of refusing
  the page (callum-reid was refused for it on every pass). A second page
  title goes; a leftover "not investigated yet" becomes bare `Unknown`; a
  History past 16 lines folds its oldest years into one line each; an
  `investigation:` citation goes from project and skill pages. A page is
  refused for size only past 30,000 characters and longer than before.
- **A citation that resolves is kept.** Inline ids (`[outlook:3a09…]`,
  (`` `project-source:…` ``)) become numbered citations before Facts are
  checked; mail rem holds in `rem.db` or `.state/mail` counts even when the
  turn was not handed it; a raw provider id is written as its digest, a
  backticked id without backticks, and `file:/x@<short hash>` pinned to the
  file's SHA-256 when that hash names its current content. An id that resolves
  nowhere still goes. Maintenance records what code dropped (`review.json`:
  `repairs`), keeps the pages it refused under `refused/`, and is handed the
  later messages in its batch's threads (`thread-tail` items).
- **A hash-pinned local file is a source on any page**:
  `file:/path#sha256:<current hash>`. The job-followup skill page cited its
  applications log this way and was refused, because only project pages took
  `file:` ids.
- **The runner dates sources.** Each source is listed once, under one number,
  dated from its original in the notebook's timezone; the audit had found one
  mail cited as `[1]` and `[2]` with two dates, and dates the writer typed that
  matched no message.
- **Every turn is told today's date** (`Today is 2026-10-15 (Australia/Sydney)`),
  and that an event before it is history, never an open thread. Corin's page kept
  13 and 14 October events open on the 15th.
- A one-page sync turn that keeps less than 60% of a page's characters, or of
  its cited sources, keeps the old page (pages under 1,000 characters are
  exempt): projects/connectonion went 14,356 → 4,132 characters in one
  accepted turn on 2026-10-13.

## co rem status (#1996, #2008)

- Every time is in the notebook's timezone (`schedule.timezone`), the last run
  included; UTC only when none is saved.
- A run whose process is gone on this machine (Ctrl-C, a closed terminal, a
  kill) shows **interrupted** at once. Status stays read-only: the next command
  that writes runs closes the record, as before.
- Today's tokens add up every run that reported usage — investigations
  included, which the day's total used to leave out — and say
  "N runs without usage" instead of turning the total into "unknown".
- `People ●○○○○○○○○○  3 of 82  4%` is the census above, the same as the reader.
- The budget line says its unit: points are percent of the Codex week, moved by
  investigation runs only. Maintenance runs are bounded by the daily call cap,
  so a day of maintenance tokens beside "0 of 10 points" is not a contradiction,
  and the line now says so.
- `Next` is the first thing under "To write next" (`co rem investigate me` on a
  notebook whose own page is still mapped), then `start` or `logs` as before.

## How co rem's results are laid out (1.9.0a9)

`status`, `doctor`, the `sync` summary and the map `init` prints share one
layout, so it is learned once:

```
co rem status · running in background (launchd)
  next slot 07:00

Today            7 pages changed · 248 items read · 3 runs
                 1.7M tokens in · 20k out

Notebook         ~/.co/rem
  People         ●○○○○○○○○○   46 of 312   15%
  Skills         ●●●●●●●●●●  154 of 154  100%
                 ● written  ○ mapped, not written yet

Mailboxes
  ✓ Gmail        read by the daily round
  ✗ Outlook      connected, but not read by the daily round (not subscribed)
                 → co rem sources add outlook
```

- One title line; what the state asks for goes under it, not after it.
- A section label in the margin, every value at column 17, one item a line.
  Status leads with today, because the notebook consolidates overnight.
- Counts are bold and right-aligned; tokens read as `812`, `91k`, `1.7M` (the
  exact numbers are in `--json` and `co rem logs`).
- Glyphs mean one thing each: `●` written, `○` mapped but not written, `✓`
  fine, `✗` needs a fix, `↻` unfinished and resumable, `→` the command that
  fixes the line above. They print the same in a pipe; only colour is dropped.
- A long value wraps under its own column in a terminal, never at the margin.
- Colour by role from `connectonion/cli/style.py`: commands cyan, counts bold,
  paths and notes dim, the green of a finished state as the one accent (the
  meter, `✓`, every progress bar), yellow for what needs a fix.
- Progress: one live line per stage (spinner, what it is doing, a 24-cell bar,
  `i/N` bold, elapsed dim); a finished stage leaves `✓ what it found`.

## What `sync` prints, and where the tokens went (#2043, #2044)

`co rem sync` says each page's outcome as it finishes, not in a dump at the end:

```
  Investigating people/ada-1f2e3d.md…
✓ Updated people/ada-1f2e3d.md (accepted)
✗ Refused people/bob-4a5b6c.md: over 20,000 characters
```

and ends with a short summary instead of the whole run record: new material
read, the pages updated / refused / with nothing new, how many are left, the
mail archive if a sync is still saving it, the run's tokens, and the command
that shows the full record (`co rem logs RUN`). Off a terminal the words are
the same, without colour. A long investigation off a terminal prints a stage
once when it starts (`Investigation: gathering codex sessions`), not once per
40 files scanned.

`co rem logs --usage` puts every model run under a stage, so the stage totals
add up to the total: `extract` and `maintain` for sync batches,
`investigate` for people, organisation and owner investigations (by hand or in
the daily round), and `projects` for project pages. A run recorded before it
split its usage by stage is counted under the stage its kind implies. Tokens are
credited to a source only by a sync batch that read that source's items; an
investigation reads many sources and is not split across them. Tokens per 1k
characters is measured on sync batches only: an investigation's material goes
into files the model searches, so its characters are not what it read.

## Refused pages and the daily round

**One refusal ledger** (`.state/refused-investigations.json`). Every path that
can refuse a page writes it: an investigation and each of its rounds, a skill
page, the project writer, and a sync's one-page turn. Before, only
`investigate()` did: the 2026-10-10 notebook ledgered one of eight refused
pages. A sync's refusal also holds the batch's material for that page, from
every source, because the cursor moves on and the batch is not read twice. A
refused round inside an accepted investigation stays in the ledger with the
sources no later round read (Corin Marsh's and Briar's, 2026-10-10 and 10-12), and
the daily row shows it as `refused_rounds`.

**Retries.** Every later run of the day retries ledger pages neither refused
nor retried in the last 20 hours, oldest refusal first: from the held material when a sync refused it, otherwise by the
page's own investigator. A page refused three times on the same material waits
for new material, so a refusal that will always happen does not cost a turn a
day for ever. An accepted page clears what it read.

**The first run of the day** sends each page to its own investigator: people to
the person investigation, `skills/catalog/` pages to the skill investigator,
projects with messages pending to the project writer, and the rest to the
older mail search. Skill pages had gone to the mail search and come back
`nothing_found` on 2026-10-11, 10-13 and 10-14. A page with nothing to write
from rests a week (`.state/nothing-found.json`) and takes no slot. When no page
is accepted, the reason says which: `nothing_found`, `refused`, `failed`,
`nothing_unfinished` or `no_page_fits_budget` (2026-10-13 said
`no_page_fits_budget` when every page tried had found nothing).

**Fewer wasted sync turns.** Measured on the 2026-10-10..15 notebook:

| Found | Now |
|---|---|
| A batch reads the first source with anything new; Codex always had some, and in 26 syncs Claude Code, Gmail and Outlook were never read | each sync starts at the source after the one it read last |
| "browser" and "connectonion" are words in nearly every session: projects/browser got a turn on 12 of 26 syncs, 9 of them NO CHANGE, 5.36M tokens | a project page with folders is routed by folder only and written only by the project writer |
| projects/connectonion was rewritten at 06:05, 07:10 and 08:05 on 2026-10-13 for 1–3 messages each | the project writer updates a page at most once in 20 hours unless 10 messages wait |
| a page whose turn changed nothing got the next batch again | it rests a day (`.state/no-change.json`) |

`scripts/rem_trial_audit.py` counts what the run records used to hide: sync
maintenance refusals missing from the ledger, refused turns in task folders
that no run names, refused rounds inside accepted pages, pages that shrank
below 60% in one turn, and churn (a page worked more than three times in three
days, with how many of those changed nothing).

An unexpected failure in an investigation keeps its traceback (the last 4,000
characters) in its run record, for `co rem logs`: a UnicodeDecodeError on a
real project page said only its type.

## Tidying a notebook made by an older version (#1999, #2008)

Maps get better, and the pages an older map made stay. An upgraded notebook
kept services as people (Apple ID, `notify@x.com`, GitHub's `unsub+…` reply
addresses, D&B, Microsoft), two of the owner's own addresses as people still
queued for investigation, three pairs of pages for one skill, and old pages
still carrying `web: not searched …` and `investigation:coverage` citations.

**Tidy runs by itself**, at the start and again at the end of every map
(`co rem init`; the pass at the end leaves the owner's own addresses to the
next run, because the map has just asked about them), and at the start of every
sync (the daily round and `co rem sync`), under the notebook lock. It is
idempotent: a tidy notebook is left exactly as it is, and nothing is written
when nothing needs tidying. No model is called. What it does:

| Found | Done | Undo |
|---|---|---|
| A people page for a service or automated sender, never investigated (the map's `automated_correspondents`, the #1987 service rule, or an automated address) | moved to `.state/archived/people/…` | move the file back |
| A people page for an address that is clearly the owner's: never replied to, and the address or display name carries the owner's name or an address the owner already confirmed | folded into the owner's page (`merge.merge_into`: written lines kept, page archived, record an alias); the address added to the owner's addresses | `.state/aliases.json` names the archived copy |
| Two catalog pages for one skill (a `SKILL.md` without a `name:` takes its folder's name, so `~/.codex/skills/changxing-nonfiction-refine` and `~/.agents/skills/nonfiction-refine` were two skills) | folded into the page of the named skill, as the map does for copies | as above |
| An organisation page for a mailbox provider (`gmail.com`, `yahoo.com.hk`, `outlook.com.au`, `qq.com`, `163.com` …) or an event platform's relay domain (`luma-mail.com`), never investigated | moved to `.state/archived/orgs/…` | move the file back |
| An organisation page for the owner's own company — a domain the owner writes from, or one named like the Company or Signing entity on the owner's page (`orgs/openonion-ai`, `orgs/connectonion-com`), never investigated | moved to `.state/archived/orgs/…`; the map makes none and the queue skips it | move the file back |
| A citation of a coding-session line the user did not type (a scheduler's `claude -p` prompt, REM's own model-access probe cited four times on the owner page) | the citation and its Sources entry removed; a line resting on it alone goes, a contact field says `Unknown`. Each session line is checked once (`.state/typed-sources.json`) | the removed lines are in the log |
| A line `- web: not searched …`, or a `Sources` entry `[N] investigation:coverage …` and its `[N]` markers | that line or marker removed; every other line kept | the removed text is in the log |

An investigated page is never archived or folded: a person's work on a page is
not undone by a rule about its address. Every action is appended to
`.state/tidy.json` with the page, what was done and, for removed lines, the
line itself. The sync result and the map report carry `tidied`, what moved, by page.

A real person is never folded into the owner. **"Possibly yours"** — the
addresses `init` offers to confirm with `--mine` — lists only addresses that
never replied *and* carry the owner's own name or confirmed address in the
address or its display name. The owner's notebook offered seventeen, fifteen
of them colleagues and friends who answer on other channels; the list now holds
the two that are the owner's. An address confirmed once (`--mine`, or folded by tidy)
stays the owner's at the next map without repeating `--mine`.

**Why twice (#2018).** The 1.9.0a5 acceptance run's map made
`team-telnyx` (`discover@telnyx.com`) and held pages for Workday's OTP sender,
Singapore Airlines' `booking@`, Lebara's `mylebara@` and Telnyx's `portal@`,
and tidy, run before that map, had nothing to act on. The map and tidy ask one
question (`map.service_page`), and it now also covers:

- a role desk that only writes in: `portal@`, `booking@`, `bookings@`,
  `reservations@`, `discover@`, `otp@`, `verify@`, `security@`, `account@`,
  `orders@`, `welcome@`, `members@`;
- a sending platform (`myworkday.com`, `workday.com`) or an `otp.` sending
  subdomain, the way `mail.` and `news.` already were;
- an address whose local part carries the domain's own name (`mylebara@lebara.com.au`)
  and that the owner never wrote to;
- a display name with the domain's name anywhere in it ("Team Telnyx"), not
  only first.

So a fresh map makes none of these, and tidy at the end of the map archives a
page the map before it made. **A mailbox provider is never an organisation**:
the list of known providers is kept, and a provider's name under any country
suffix (`yahoo.com.hk`, `hotmail.co.uk`, `outlook.com.au`) is one too; an event
platform's relay (`luma-mail.com`, 253 mails from one sender) makes no
organisation either.

**The owner's page is rewritten, not appended to (#2017).** The acceptance
run's owner page carried nine "Possibly also the owner's" lines, the same
three addresses at different counts, two of them already confirmed and folded,
and History still said "In the 90 days to 2026-09-25" after a re-map. Each map
now replaces every "Possibly also the owner's" line with the current list, and
replaces its own History lines ("In the N days to …", "Most mail with …",
"Coding sessions in the same window …") and its `[1]` enumeration source with
today's. Tidy drops the line of an address it confirms or folds. Other lines
are never touched.

Measured on the same copy after 1.9.0a5's tidy (never the notebook itself):
people pages 357 → 349 (8 more services: Telnyx's portal, Singapore Airlines'
booking desk, both Workday senders, Lebara, TEN13's community desk,
"Partnership LexGeneris", "Swim School UNSWFAC"), held pages 25 → 19,
organisation pages 142 → 140 (`yahoo.com.hk`, `luma-mail.com`), "Possibly also
the owner's" lines on the owner's page 9 → 0. A second pass changed nothing.

A fresh map no longer makes the duplicate skill pages either: a skill named
after its folder joins the named skill whose name its folder ends with
(`changxing-` + `nonfiction-refine`) when the two copies are the same file or
carry the same description.

Measured on a copy of the owner's notebook (2026-10-01, never the notebook
itself): people pages 381 → 357 (22 services archived, 2 own addresses folded),
skill catalog pages 153 → 150, "possibly yours" 17 → 0, pages with
`web: not searched` 4 → 0, pages citing `investigation:coverage` 5 → 0 (9
lines removed). A second pass changed nothing.

## Paths
- /home/you/projects/connectonion
- Worktrees: 49
- Sessions: 116
```

The main checkout is one branch's working tree, not the project's state (#1982).
On the owner's machine it sat on an August branch, and the page said version
1.8.0a3 the week 1.9.0a3 shipped. So an investigation hands the turn one
`checkout-state` item per listed checkout, cited as `git:<path>`: the branch it is
on and its HEAD's commit date, the project's current line (`origin/HEAD`, else
`origin/main`, `origin/master`, `main`, `master`, else the most recently committed
branch) with its last commit date and the version in its `pyproject.toml` or
`package.json`, and -- when HEAD is more than 14 days older than the project's
newest session -- a line saying the checkout's files are not the current state
and the version comes from that line instead. The file list is unchanged; the
turn is told which of what it reads is stale.

Some folders are not projects, and the map leaves them out (`not_a_project` in
`rem/scan.py`):

| Folder | Why |
|---|---|
| your home folder, or above it | it holds every session there is (#1944) |
| inside a hidden folder (`~/.claude/plugins/cache/…`, `~/projects/.artifacts/…`) and not a git repository | a cache, a plugin install or build output |
| a Claude Code scheduled-task folder (`…/scheduled-tasks/…`) | a task's working folder |
| not in a git repository, one session, at most 3 messages you typed | a one-off chat (`create-a-scheduled-task-called-weekday`, a plugin install folder) |

A folder with two sessions, a repository, or a longer conversation stays a
project. System temporary directories, removed Codex worktrees, co rem's own task
copies, fixture notebooks and multi-repository workspace containers stay out as
before.

A notebook mapped before this has split and junk pages. The next map merges
them: every existing page listing one of the repository's paths (worktrees
compared as their main checkout) folds into one page — the one with the most
written content, so an investigated page is never merged into an empty one.
Written lines of the other page are merged section by section with citations
renumbered, its message material under `.state/projects/` is merged too, and the
page itself moves to `.state/archived/` with its record kept as an alias
(`.state/aliases.json`). A junk folder's page that holds only map output is
archived; one somebody wrote in is kept.

### Preview reliability checks

Initialization reports partial failure with a nonzero exit if a selected mail source cannot be initialized or read. Completed maps remain available; provider error text is not exposed. Recovery commands retain the notebook root. Automated-looking correspondents are explicitly labelled candidates, not silently certified as people.

Your own page has its own spec (#2008), the `rem-owner-page` Skill, composed
after the person page only for `investigate me`. It leads with who you are and
what you are working on now, from your coding sessions (the projects and what
you did in them, dated); your roles appear only when you state them about
yourself or someone states them about you, never from a list you wrote about
someone else (a real page took "Partner at OpenOnion, running marketing" from
the owner's own description of a partner); `Open threads` is what you owe and
are owed; `History` is dated events, not the map's mail counts. It has no "How
the user writes to them" section. The same attribution rule is in
`rem-investigate-person` for everyone: a role in a list the user writes about
someone else is that person's.

init runs the whole `co rem investigate me` for you. `--quick` is a bounded
pass that samples recent items across available source types and labels the
result partial; it is only for `me`, and neither mode approves a candidate
without review.

`co rem investigate <page> --days 5` reports source gathering, evidence
preparation, extraction chunk counts when the material exceeds one model turn,
and candidate writing in its run log and terminal. A failed model or provider
call exits nonzero and keeps the page unchanged. Project investigations may
inspect a fixed, bounded snapshot of files collected from the page's recorded
local Paths; the candidate file inventory is a lead, not a citable original or
proof of file contents. Review the candidate and its
citations before treating it as a verified notebook page.
Completed extraction chunks are checkpointed under `.state/extracts/investigate/`;
rerunning the same evidence and model settings can reuse them after an
interruption. The running log records the current chunk and usage from completed
chunks. A changed source or extraction prompt invalidates the checkpoint.

Repeated mapping refreshes generated project counts, dates and paths while preserving written notes. Skill pages retain authored descriptions and show current installed metadata in a separate managed section. Unchanged content is not rewritten. Equivalent SSH/HTTPS Git remotes share an identity; distinct case-sensitive repository paths remain distinct. Search groups skill installations just like the catalog, and the homepage labels its content as a snapshot rather than claiming every skeleton is maintained.

## Reflections, review and staged investigation

See [co rem memory workflows](rem-memory.md) for `reflect`, `review`, `capture`,
`route` and `daily`, including provider, retention and budget limits.

### Writing languages

`co rem init` prints the owner languages and where they came from; the reader
shows them under Reader settings, and `co rem config` shows any configured list.
Detection uses your sent mail and typed sessions.
`co rem config set languages zh,en` overrides detection; an empty list restores
it. `co rem init --languages zh,en` sets the same validated configuration before
the map. The first non-English tag supplies automatic translations, including a
secondary Chinese language. 中文 mode also reads regional Chinese caches such
as `zh-TW` and `zh-CN`. English pages remain the canonical audit record.

### Cached page languages

After refreshing the owner's languages, each daily run translates pages changed
by maintenance or investigation into the first non-English language in
the owner's languages (configured or detected), when the runner is ready.
`limits.translations_per_day` defaults to **10** new translation attempts across
all daily slots; current cached translations use no attempts. Set it with
`co rem config set limits.translations_per_day 5`. Failures are reported per page
in the maintenance result and daily translation run log, and the next page continues.

The reader uses current cached prose for its selected interface language and
shows the original when no translation is available. Rendering never starts a
translation. The per-page Read in menu still allows an explicit language choice.
Quoted evidence stays exactly in its original language.

To backfill existing pages once (the English pages remain the audited source):

```bash
co rem translate --all --to zh
co rem --root /path/to/rem translate --all --category people
co rem translate people/avery-lin.md --to zh
```

Omit `--to` to use the owner's first configured or detected non-English language.
`--all` translates people, orgs, projects, decisions, principles and skills,
using up to `limits.workers` concurrent pages. It skips current caches, logs/activity, catalog indexes, duplicate
installations and unlisted records. `--category` selects one of those six types.
Each page prints `translated`, `cached`, or `failed: reason`, followed by counts.
A page's reported translation failure does not stop the next page; any failures
make the command exit 1. `--json` returns the outcomes and counts instead.
Open or refresh the reader afterward: 中文 mode shows current cached prose, with
quotes in their original language. An untranslated record still shows **原文**.


Each model translation records a `translate` run with its language, page,
duration, harness/model and usage, including failed attempts with reported
usage. `co rem logs --usage` includes these costs; daily translation summaries
retain attempt counts without duplicating the per-page usage.

Reader settings shows **Notebook languages: 中文 · English — detected** (or
**— set**) with a copyable `config set languages` command. Reader commands keep
the selected root, shortening a root under your home to `~/…` with shell-safe
quoting. The home translation notice is a fallback based only on written pages.
When the last init or daily translation reported failures, it names how many
pages could not be translated and offers a copyable `translate --all` command.

### Codex history during maintenance

REM archives its internal Codex threads after each model call, including failed
calls when the provider remains responsive. A forced cancellation or process
crash can leave a thread active; existing history is not bulk-archived. They leave the active conversation list while their trace and session ID
remain available for explicit resume and `co rem logs`. Before resuming, REM
unarchives the thread, then archives it again after the turn. Ordinary interactive Codex
threads are unchanged.
History archiving also applies when launchd owns the timer. In rc21, eligible
Codex notebooks use Codex desktop Scheduled; see [Scheduling](#scheduling-and-accounting)
for eligibility and fallback. Registration uses the desktop's task file format;
Scheduled is not a public App Server scheduling API.

### Unchanged-content audit continuity (1.9.3rc17, #2639)

1.9.3rc17 narrows the protection for content inherited from an
accepted page. It compares complete retained prose contexts, including meaningful
word spaces, the page title and section hierarchy, and exact cited original IDs
at their relative text positions. Renumbering or line wrapping can preserve
continuity; removing a condition, moving evidence to another sentence or moving
history into current context does not. A removed or reordered old paragraph or
bullet invalidates its section's exemption, so adjacent qualifications cannot
silently disappear. Headings, fenced examples and Sources rows do not count as
old prose. Every occurrence of a finding must qualify, including new duplicates.

Unchanged findings can remain deferred under the existing preservation policy,
but are recorded as **insufficient**, with a deferred count in `review.json`,
not as a factual pass. Active findings reach ordinary repair/refusal even if the
model labels its top-level verdict PASS or INSUFFICIENT.
This is a deterministic continuity check, not semantic equivalence or proof the
old content is true. Additions may still affect discourse meaning; actual model
and current native desktop/phone/accessibility acceptance remain unverified.
Existing notebook pages are not automatically corrected.
