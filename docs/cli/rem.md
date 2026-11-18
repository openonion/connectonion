# co rem — command guide

**Start with `co init`.** It runs the same first notebook build as `co rem init`, which maps the last 180 days and investigates
every eligible page. Run `co rem status` to see coverage and `co rem open` to
read it. A refused page stays visible in the run history with its retry command.

Jump to [Start here](#start-here) · [Commands](#commands) ·
[Source controls](#source) · [Scheduling](#scheduling-and-accounting) ·
[Reader layout](#what-the-reader-shows).

Check your installed release. The exact commands are
also available through `co rem --help` and each subcommand's `--help` page.
Old command names (`unfinished`, `people`, `daily`, `subscribe`, `subscriptions`,
`unsubscribe`, `route`, `usage`) remain compatibility aliases and print their new name.

## What it is

**co rem enables decentralized context flow.** It connects context from your
mail (connected with `co auth google` or `co auth microsoft`) and your local
Codex and Claude Code sessions in linked Markdown pages about people,
projects and tools. Those pages stay on your machine, with links back to
the evidence. You and your agents can read and reuse them in the next task.
Memory keeps context available over time; carrying context through your
work is the purpose.

On macOS, one-page agent tasks also receive a **Recently read** index from the default
Chrome profile: visits in the last 30 days matching the subject's name, domain
or GitHub repository. Titles and URLs are leads. A relevant page must be fetched
with `co fetch <url> > web/<slug>.md` and registered in `web/sources.json` before
its content can be cited. An address registered without its scheme
(`example.org/team`, `www.example.org`, `//example.org/team`, or one wrapped in
spaces or `<>`) is read as `https://…`; it used to refuse the page and cost a
whole repair turn (474 s and 2.98M tokens on 2026-11-16, #3083). Anything else
that is neither an HTTP(S) URL nor a native source ID is refused by entry:
"Research captures need an HTTP(S) URL or a native read-only source ID: entry 2
of web/sources.json (file team.md) has "search: …"; write the page's exact
address as "url": "https://<host>/<path>" …", and an entry that is neither
(a `file:` id) is to be removed. That refusal goes back to the writer for a
repair turn like any other review finding; it used to fail the page outright
(610 s on 2026-11-16, with no repair). The index itself opens no pages and makes no network
requests; the existing LinkedIn restriction still applies. It shows up to 50
distinct URLs, newest first, with repeated visits collapsed. Profile/resource
links match that specific page; an explicit website or organisation domain
matches the domain and its subdomains.

Inspect history directly with `co browser history --days 1 --json`. The default
window is 7 days; `--domain SITE`, `--query TEXT` and `--profile NAME` narrow the
results. Each row is a visit, including repeat visits, with a UTC time, title and
URL. `--domain` includes subdomains; `--query` matches literal text in the title
or URL, ignoring case. Both filters together must match. REM currently uses
Chrome's `Default` profile. Configurable domain exclusions depend on #2830.

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
co init                     # Grant sources, install upkeep and build without questions
co rem status               # Check notebook coverage and upkeep
co rem init                 # Map sources, then investigate your people, work and installed skills
co rem open                 # Read your page
co rem start                # Approve sources if needed and install or resume upkeep
```

Global `co init` never prompts. It records an init consent grant, reads all
already authenticated Google/Microsoft mailboxes and local Codex / Claude Code
sessions, installs upkeep and builds in the foreground. The estimate is
informational. `--yes` and non-TTY runs behave identically. With no mailbox,
it continues on sessions and prints `co auth google` / `co auth microsoft`.
Mail connected later joins the next scheduled round without further approval;
explicitly removed sources stay removed. Without a supported scheduler it
still builds and prints guidance for manual scheduling.

The final summary reports mapped and written pages and names the scheduler.
Its undo block lists `co rem stop` to disable upkeep, `co rem sources` to see
sources and `co rem sources remove SOURCE` to remove one, and `co auth logout`
to remove OpenOnion credentials. Mailbox access can be revoked in your Google
or Microsoft account (there is no CLI disconnect command). Stop upkeep before
deleting the notebook folder, `~/.co/rem`.

`co init --no-rem` skips REM. Repeating global init leaves existing REM
unchanged; `co rem init` reruns the build. `--background` uses the same REM step,
and project setup (`co init ./`) does not initialize REM. Standalone
`co rem init` prints the summary, undo block and estimate in a terminal, then proceeds without pausing.

The full first run is one command (#1943). Before mapping, `co rem init`
checks runner availability and prints the source/model/schedule summary.
Consent changes print a diff, then proceed in a terminal. Noninteractive runs
ask nothing; first consent requires `--yes` unless an existing grant applies.

Init maps 180 days of connected mail and approved local Codex / Claude Code
sessions, saves the private mail material, then prints your own page's header
facts — who you write to most, how much mail, and which projects you have been
coding in — with the page's path. These facts appear after the map and archive
finish; their timing depends on source volume and mailbox response times.
After printing the estimate, init summarises pending sessions, checks model
access and writes a quick first pass of your page. The full owner pass then shares the worker queue with
the selected pages. Both owner passes use your sent mail and coding sessions
from the last 30 days by default, or the window given with `--days`. There is
no fixed completion time: evidence volume, model throughput, repairs, configured
per-turn timeout, and worker contention affect it. The full pass can read the
evidence in several model turns, so the per-turn timeout is not a deadline for
the whole owner page.
Next come all eligible mapped people, recent
first, each investigated from up to two years of their mail; queued projects
already listed in the map, recent first; all pending mapped organisations; and
installed skills from source and retained run evidence: 16 pages at a time.
After the map summary, init prints your notebook languages and whether they
were detected from your sent mail and typed sessions or set in config. Use
`co rem init --languages zh,en` to set them before mapping, or
`co rem config set languages zh,en` (your list, as init prints it) to change them
later; `languages en` keeps English only. English remains the
canonical writing language. After tidying and drawing decisions, knowledge and principles,
init translates every listed, written page into your first non-English language,
even when English is first in the list. Mapped-only stubs and the skill catalog
index are excluded. `--no-translate` skips this last step; `--no-investigate`,
`--estimate-only`, English-only languages or an unavailable runner also skip it
with a reason in JSON. JSON includes `languages` and a `translation` summary.

The estimate includes one translation per selected page plus your page, with
unknown decision/principle counts treated as zero. Translation uses its own
`limits.workers` lanes after the investigations, so its wall time is added to
the page queue. Completed translation runs in this notebook supply median rates;
otherwise planning uses 90,000 input tokens and 200 seconds per page (measured
2026-10-21 on a 297-page notebook at 16 workers: one translation alone takes
22–40 s, but concurrent turns share the model's throughput; the whole notebook
took 66 minutes). First-run translation has no daily cap.

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
organisation 2.0M and ~8.5 minutes, a skill 800k and ~3 minutes. The owner
rate is scaled by mapped mail items plus usable sessions from the map's
parsed material. Only approved session sources count; program prompts and
temporary directories do not. Estimate-only uses that same parsed material
without importing it. Zero material means zero owner cost; without
a mailbox address the owner page is excluded, with a one-line explanation.
The scaling uses a planning assumption: 2,000 items reach the full rate of
6.5M and ~35 minutes per owner turn, capped there; smaller maps use a
proportional share of the notebook's median or the default. The quick and full
turns are both counted. This source-volume scaling is an estimate, not a
measurement of per-item cost. The
full-run rates alone announced ~42 minutes and ~50M tokens for the release
check, which took 82 minutes and 102M; at the full owner rate the estimate
says 95 minutes and 100M. It does not predict every retry or refusal. Minutes are
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

If the map finds no people or projects, installed skills alone do not start a
first-run page queue. Init exits successfully without an estimate pause and says:

```text
Nothing to write yet: connect a mailbox (co auth google|microsoft) or work in a project with Codex, then run co rem init
```

The agent-session summary includes skip reasons, for example `3 skipped
(program prompt)` or `2 skipped (temporary directory, outside window)`.

Your page is titled with what you are called: `--name` if given, else the
name the people writing to you put on your address (the To and Cc of mail you
received; spellings that differ only in case are one name, and a name that is
just the address is not one), else the From name of mail you sent, else the
name a mailbox has configured (#2008). For example, a fictional mailbox may
be configured as "Rowan A", while correspondents write "Rowan Ashdown".
A new notebook names the file after you (`people/rowan-ashdown-….md` in that
example); an existing page keeps its path.

Progress shows the mail scan and body archive counts, then a live total bar and
completed counts for You, People, Projects, Organisations and Skills. Each page
prints a result line. The scan steps are kept in `.state/init-progress.log`.
Addresses that look like yours (you wrote,
nobody replied) are listed on one line with one command that confirms the ones
you keep: `co rem init --mine a@example.org,b@example.org`. Mailboxes init read
are subscribed, so they appear in the source summary. `co rem start` reuses
unchanged consent recorded by init; when sources or anything else in the
summary changes, it prints the diff and proceeds in a terminal. On a notebook without prior consent,
start approves access, runs one bounded sync, then installs the schedule.
With consent already recorded, start installs or resumes upkeep without an
immediate batch; run `co rem sync` for an update now.

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
co rem collect --dry-run    # Inspect pending metadata, without running a model
co rem collect              # One batch of new material only
co rem sync                 # One update: new material, then at most one unfinished page
co rem logs                 # Inspect results, partial coverage and failures
```

Normal output uses readable labels and plain page paths. Empty lists explain
what is missing; unknown usage remains **Unknown**, never zero. Results end
with a copyable `Next:` command, including the selected root and shell quoting.
Use `co rem --help` as the workflow guide: it gives task selection,
observed inputs, expected results, source/quality checks and recovery before
the command inventory. `init --help`, `investigate --help` and `collect --help`
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
| Update and review | `collect`, `sync`, `catchup`, `capture`, `reflect`, `reflections`, `propose`, `review`, `decisions`, `abstract` |
| Sources and background | `sources`, `sources add`, `sources remove`, `start`, `stop` |
| Settings and diagnostics | `config`, `config set`, `logs`, `doctor` |

`co rem init` reviews consent before the map and installs upkeep after a
successful first run, without repeating the first sync. Global `co init`
installs upkeep before building the notebook. In a script, `co rem init --yes`
supplies approval; without it, new consent is deferred. `init --no-start` leaves
background work off, and `init --estimate-only` skips model work and schedule
installation but still reviews source consent before mapping.
If a selected page fails or is refused, init reports a nonzero exit. When upkeep
was off, `co rem init` leaves it off until the unfinished pages are repaired.
An already installed schedule stays on.
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
`init`, `co rem skills map` and the start of every night round recount it, so
the count and the last day follow the sessions instead of stopping on the day
of init.

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
The Skills page is one table, the same one People and Organisations use
(#3094): a row per skill, one line high, with **Skill**, **What it does**,
**Family**, **Last used** and **Times used · 180 days**. Headers sort,
**Columns** hides a column, and a row opens the skill's page.

- **Family tabs** sit above the table: **All** first, then each name family
  with its count (Lark, LinkedIn, co …; a family of fewer than three skills
  goes under **Other**), the largest first. A tab shows only that family, and
  the choice is in the address (`#c=skills&family=Lark`), so Back and a
  bookmark return to it.
- **Views** beside the page's name re-order the table in one click: **Most
  used** (the default: times used, ties by the page's latest date), **Recently
  used** (`&v=recent`) and **By family** (`&v=family`: every family under its
  own sub-head with its count, the busiest skill first). A header click still
  sorts inside the view you are in.
- **The finder** (*Find among N skills…*) filters within the current tab, on a
  skill's name, its line and its page; Enter opens the first match.
- **Last used** is in words (*Yesterday*, *3 weeks ago*, *2 months ago*; the
  date is one hover away) and **Never** in grey for a skill with no match in the
  window. **Times used** is the skill-name match count over the usage window,
  which its header names (as People's *Messages · 90 days* does); there is no
  caption about how the count is made.
- There are no **most used** cards any more: with Most used as the default view
  the first eight rows are those eight skills, and two rows of cards pushed the
  table below the first screen at 900 px.

Each skill's line is the first clause of its description, in the reader's
language when the skill has its own text in it or a translation is cached;
otherwise the original. A skill with no description keeps its row with that
cell empty. A row keeps the "last night" marker for a page last night's pass
rewrote and "N installed copies" beside the name when the skill is installed in
more than one place. On a phone the tabs are one row that scrolls sideways and each skill
is two lines: its name with last used and times used at the right, then its
line. A skill page keeps the match details, scope
explanation and usage bar, and names where the skill lives in words (Claude
Code, Codex, shared agent skills, ConnectOnion) with an "Open SKILL.md" link.

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

The five stages of a REM day are:

| Stage | Verb | What it does | Background runs it (scheduled sync / exec / in-session next) | Budget it spends |
|---|---|---|---|---|
| Collect | `co rem collect` | Read one batch of new mail and coding sessions into the notebook; no later stages. | Yes / yes / yes | Source reads are model-free; extraction uses the daily call cap. |
| Investigate | `co rem investigate` | Fill pages from originals: people, organisations, projects, session summaries, same-person checks and reply drafts. | Yes / yes / yes | Investigation's weekly points and usage floor; background daily call cap. |
| Deepen | `co rem deepen` (one page: `enrich`, `muse`) | Follow unfollowed leads, then think a page through. | Yes, after the round / yes, once a round: after its first portion of investigation, or after the round when it had none / no: single tasks use the session's own model and cannot run an hour-long slot; the `codex_exec` launcher runs the slot when a turn ends | Separate weekly deepen points, usage floors, page count, workers and slot time. |
| Abstract | `co rem abstract` | Decisions, settled knowledge and experience, then principles, out of notebook pages. | No separate abstract round in legacy sync / yes / yes | Background daily call cap and `limits.abstract_rounds_per_night`; manual write ignores the nightly cap. |
| Translate | `co rem translate` | Put changed pages into the owner's language; last in the intended day because earlier stages change pages. | Yes / yes / yes; a `daily-translation` round only translates | Separate daily translation cap; model-provider allowance. |

`co rem collect` reads one batch, not until caught up. The default ceiling is
40 items (`limits.extract_items_per_batch`) from one source, with an additional
input character bound. Sources rotate between batches. Mail takes whole
correspondents by their oldest queued mail; a correspondent larger than a batch
is sliced oldest first. Run `co rem collect` again for another batch.
The result reports known mail still waiting and a copyable next command.
As on the existing batch path, approved coding sessions are also imported and a
stalled init mail archive can resume for up to five minutes across approved
mailboxes. These reads are outside the extraction batch; `--source` scopes that
batch, not this existing housekeeping.

Mail `progress.json` → source → `pending` contains message metadata already
listed but not yet successfully processed in a batch. It is not a count of all
unread mail in the mailbox or of unlisted sessions. Automated senders excluded
by the subscription never enter this queue; deleted messages are removed on a
404. Disabled or unapproved sources retain their queue but are reported as held,
separately from waiting mail. `--with` leaves other correspondents in place.
Read failures, a daily call cap, and an input that cannot fit can delay progress;
there is no age expiry for queued mail. Existing local corrections and captured
material take priority over source batches, so a sustained local backlog can also
delay mail. Rejected page material is retained in
refusal state after a successful batch advances its mail queue.
In the native round a batch's page that is parked (refused twice for one reason,
or three times) does the same: the batch's scan point is saved, and the parked
page keeps that batch's material in the refusal ledger for its retry, so one
page that cannot pass its claim audit no longer sends the same mail through
extract and maintain every round (2026-11-16: 40 mails read five times in a
day, the scan point nine days behind). A batch is still left unsaved when its
extract task or any task that is not a parked page is discarded; then the
batch's run record carries `progress_not_saved` with the reason, and
`co rem status` says for that mailbox `read <date>, but its progress was not
saved (<reason>); the same mail is read again next round` instead of "not read
since".

Compatibility command `co rem sync`: Collect, then investigate what is unfinished;
use co rem collect for new material only, co rem catchup for a whole day.
Its existing options and behavior remain, including installed schedules calling
`co rem sync --scheduled` and the batch-only `--source` / `--all` paths.

The stage order above describes the day. The current native round preserves
its trialled order: collect, new same-person checks and reply drafts, then
investigation in portions of 2 turns. Between two portions the other stages
take their turn: one session summary, one Abstract round, then translation's
share (`translation_share`: a tenth of the pages waiting, at least 10). After
the queue come the remaining session summaries and Abstract rounds, the
same-person checks and the closing translation, which goes on until no page
waits.

Cheap stages are finished, not rationed (owner, 2026-11-17: "translation and
summaries cost little; there is so little content, it should all be done").
Measured on a real notebook: a translation turn takes 11 to 83 seconds and 9 of
9 were accepted first try; a session summary takes 24 to 57 seconds; one
deepen turn takes 9 to 35 minutes. The closing translation used to take one
share (a fiftieth of the backlog) and the round took five session summaries,
so four nights translated 9, 8, 9 and 0 of some 350 waiting pages. Now a round
summarises up to `limits.summaries_per_round` sessions (40) and translates
until nothing waits. What still ends it: every page is tried once a round, a
failing translation parks only its page, two faults in a row stop the round,
the Codex usage floor stops every model call, and a round translates at most
`limits.translations_per_round` pages (400), so a night always ends; at the
measured times 400 turns are about 1 to 9 hours, typically 4. When that bound
leaves pages waiting the night's line says how many. A round with nothing to
investigate (or with investigation held by its weekly budget) starts its
deepen slot once the closing translation has begun and the night has produced
something, and does not wait for the last page.

Every stage produces early in a night, not only at its end (owner,
2026-11-16). One investigation turn measured 20 to 60 minutes on a real
notebook and a 3-hour catchup night completed one page. With portions of 8
turns and everything else after the whole queue, Abstract and Deepen were 4 to
12 hours into a night, and any night that was cut short (a deadline, the quota
floor, two faults in a row, the 3-hour turn) left them at 0. Now a night that
stops after its first portion has already served a session summary, an Abstract
round and a translation share, and has run its deepen slot.

Whole-round background runners (`co rem exec`, `co rem catchup`, the
`codex_exec` launchd entry point, and scheduled sync) run the unchanged
`depth.slot` once per round. `co rem exec` and catchup run it between two
tasks as soon as the round's first portion of investigation is done: after
that portion's Abstract round and before its translation turns, so the order
is Investigate, Abstract, Deepen, Translate. The `codex_exec` launcher cannot
run it inside a turn (the session's own model is driving single tasks), so it
runs it when a turn ends, whether the turn finished, was stopped or reached its
three hours, once the first portion is done. The page under investigation and
the page of a task left pending are left out of that slot: deepening them
would change the page under its own draft. A round with no investigation
portion (nothing to investigate) keeps the slot where it was, after the round
completes, and there it still needs a night that wrote, translated or drafted
something. The early slot does not ask that: a night that served a portion is
working, and its first page may be an hour from written. Either way a round
has one slot: the one that ran early is the one a completed round reports.
Pages deepened await the next translation pass.
Legacy scheduled sync keeps its existing collect, investigation and translation
round, then deepens. A busy, not-due or translation-only round, and a round
that stopped before its first portion, do not start a deepen slot; at the
Codex usage floor the slot starts no page, as before.
`co rem catchup` reuses exec, including that same slot, once per night; it
does not add another slot. In-session `next` / `submit` keeps handing single
tasks to the session's model and never deepens.

Every stage gets its share of a night, so one long queue cannot keep the
later stages from running (owner, 2026-11-16: a queue of 333 investigations
against a weekly budget for 60 to 90 left Abstract and Deepen at 0 after eight
catchup runs). A night is the schedule's night (noon to noon) or one
`co rem catchup` night:

| Stage | A night's share | Setting |
|---|---|---|
| Investigate | 12 pages: people, projects, organisations, older pages, retries and your own page | `limits.investigations_per_night` |
| Investigate, skill pages | 3 pages, counted on their own and served after the others | `limits.skill_pages_per_night` |
| Abstract | 6 rounds of up to 20 decision lines: one between every two portions of investigation, the rest after the queue | `limits.abstract_rounds_per_night` |
| Deepen | 3 pages in the round's one slot, after the first portion of investigation | `limits.depth_pages_per_slot` |
| Session summaries | 40 a round: one between every two portions of investigation, the rest after the queue | `limits.summaries_per_round` |
| Translate | a tenth of the backlog (at least 10) between every two portions of investigation; after the queue, every page that waits, up to 400 a round | `limits.translations_per_round` |

Only a page that was handed to the model uses the share: one that is parked,
set aside for a stopped mailbox or found to have nothing new does not. A page
already open keeps going until it is written, however many rounds it takes.
When a share is used, the round goes on to what is left of session summaries
and Abstract, the same-person checks and Translate, and completes; Deepen has
run by then, after the first portion. The pages that
did not fit are not lost: they are saved in `.state/investigation-waiting.json`
and the next round puts them back in the queue. A page the round lists again
keeps the place that round gives it; a page only the waiting list remembers (a
person whose new mail predates the last round) leads, so the backlog cannot
push it back for weeks.
The night's line and status say it in words, as work that waits and not as a
failure: `12 of tonight's 12 investigations done; 319 wait for later nights`.
The two investigation shares ration expensive work. `limits.summaries_per_round`
and `limits.translations_per_round` are not rations: their defaults are above
what a notebook has waiting, and they exist so that a round has a stated end.
`limits.translations_per_day`, which D-104 retired, capped a day at a few
pages; `limits.translations_per_round` replaces it as that upper bound. The
weekly budgets and the Codex usage floor still apply on top.

A weekly budget holds its own stage and no other (owner, 2026-11-16: a catchup
night ended at "investigation has used 35 of its 35-point weekly budget" with
Abstract, Translate and Deepen not run, while the Codex week was at 37%):

| What is spent | What waits | What still runs |
|---|---|---|
| `limits.investigation_quota_points` (35) | New investigation pages and the same-person checks. A page already open is finished. | Collect and reading the batch into pages, reply drafts, session summaries, Abstract, Translate, Deepen |
| `limits.depth_quota_points` (30) | Deepen | Everything else |
| `limits.quota_floor_percent` (the Codex week at 90%) | Every step that calls the model | Collect without the model, the calendar and the day plan |

A spent investigation budget works like a used share: the pages wait in
`.state/investigation-waiting.json`, the round goes on to its other stages and
completes, and the night's line and the Investigate line of `co rem status` say
`investigation is waiting for its weekly budget (35 of 35 points used; the Codex
week resets Wed 18 Nov 22:00); 40 pages wait`. It is not a stop reason, for
`co rem exec`, the schedule or `co rem catchup`.
The investigation budget counts investigation pages and same-person checks,
by hand or scheduled. Abstract rounds are not counted against it (they were,
while they ran inside the round, and never when run by `co rem abstract`);
batch extract and maintain, session summaries, reply drafts and Translate
never were. Those are bounded by the daily call cap
(`limits.runner_calls_per_day`), `limits.abstract_rounds_per_night`,
`limits.summaries_per_round`, `limits.translations_per_round`, and the floor.
`co rem status` and that budget hold use one number: the points counted from
the run logs when status is asked, not the sentence a past round saved.

`co rem status` keeps its existing dashboard and adds five stage lines in the
order above. Each says what is waiting (a count) and when that stage last ran
in the notebook's timezone (a date or `never`). Counts come from saved source
metadata and the existing investigation, deepen, captured-decision and
translation queues; investigation counts distinct pages awaiting writing, session
summaries, same-person checks or reply preparation; collection counts listed mail waiting from enabled, approved sources. Disabled
or unapproved source queues are shown separately as held; unlisted mail and
sessions are not counted. Collection dates include batch receipts inside native
daily rounds as well as standalone batches, and ignore empty checks. A stage's sentence that would pass 80 columns
breaks after a `;` and continues two spaces in on the next line (the Abstract line's page counts, the Investigate
line's shares). The same rows are under `stages` in `--json`, each sentence whole in `text`; `calendar` and
`day_plan` carry the calendar line and the day plan line beside them.

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
| `co rem decisions` | Count decision and principle pages, captured lines waiting, written lines, merges, refusals, missing answers and skips. No model; no writes. |
| `co rem abstract [--rounds N]` | Write decisions, then knowledge learned across notebook pages, then principles for recurring reasons. Continues until nothing unattempted is left, two empty rounds occur in a row, or N rounds finish. |
| `co rem catchup [--nights N]` | Run exec, including its single deepen slot, which runs after the night's first portion of investigation (2 turns) and that portion's Abstract round, so a night that is cut short has still abstracted, deepened and translated. `--nights` repeats the whole round back to back. Calls the configured model. A night with deepen can take an hour or more. Each night gets fresh limits; weekly budgets and the Codex usage floor still apply. Prints each night's counts, including pages deepened and why none, then totals and `co rem open`. Investigates up to `limits.investigations_per_night` pages (12) and `limits.skill_pages_per_night` skill pages (3) a night, with Abstract, Deepen and Translate taking their turns between portions of investigation; the night's line says how many pages wait for later nights. Session summaries (up to `limits.summaries_per_round`, 40) and translation (every waiting page, up to `limits.translations_per_round`, 400) are finished in the night, not rationed; the line counts both and says how many translations wait when the bound was reached. A spent weekly investigation budget holds only investigation: the night still reads the batch, summarises sessions, abstracts, translates and deepens, and its line says investigation is waiting and when the week resets. At the Codex usage floor before any night ran it still collects new mail and sessions and saves the calendar and day plan, with no model call, and says which stages wait. A page whose candidate review keeps refusing is retried with the refusal, then parked: the night goes on, and its line and the totals say how many pages were parked, each cause with its count (three at most) and where the candidates are kept. A task an earlier stopped run left pending is resumed the same way, and so is a task that cannot be settled (its worker submitted it itself, its inputs changed, its turn timed out): it is parked with the error in words and the night goes on. An error that stops the round (the runner cannot run, the lock is held elsewhere) ends that night and starts no further one, after the night's line and the totals with the reason. One run at a time holds a notebook: catchup, `co rem exec` and the scheduled background turn take the same lock (`.state/exec-turn.lock`) for their whole run, and the kernel releases it when the process ends, a deadline's exit 75 included. Started while another holds it, catchup prints `Another REM run holds this notebook (the scheduled background turn, co rem exec or co rem catchup), so this run started nothing. Run it again when that one has finished; co rem status shows the turn in progress. No night was counted.` and exits 1; `co rem exec` prints the same sentence and exits 0; a scheduled fire writes it to the scheduler log, exits 0 and tries again at the next fire. Exit 0 when it finished or a limit stopped it, including a night that parked pages; 1 on a busy or failed round, or when another run holds the notebook. Leaves schedule times unchanged. |
| `co rem history [--archive]` | Inspect or archive older internal Codex investigation traces, keeping ordinary, pinned, active and recent chats. |
| `co rem start` | Print the source/model/schedule summary (a diff after changes), then proceed in a terminal. First approval runs a bounded sync and installs upkeep; after `stop`, resume without a batch. Use `co rem sync` for an update now. Noninteractive runs ask nothing; new consent needs `--yes`. |
| `co rem start --yes` | Explicit noninteractive consent for start. |
| `co rem stop` | Remove that notebook's background job; preserve pages and progress. |
| `co rem sync` | The whole update: one batch of new material; then the day's first run investigates unfinished pages, most recent first, and every later run updates only the people and projects with something new. What the schedule runs (`sync --scheduled`). |
| `co rem collect [--source NAME] [--with ADDRESS] [--dry-run]` | Read one batch of approved new material only, using the existing extraction/page updates. No investigation, deepen, abstract or translation. Dry run reads metadata only. |
| `co rem sources add codex --project /path/to/repo --since 30d` | Save a scoped source choice. |
| `co rem sources add whatsapp --chat <id>` | Read one WhatsApp chat (group or person) from the files `co whatsapp listen` keeps; ids from `co whatsapp chats`. Repeat per chat; the next `co rem start` prints the diff and proceeds in a terminal. `co rem sources remove whatsapp --chat <id>` stops one chat. |
| `co rem sources remove codex` | Disable that source. |
| `co rem list people` / `show people/alice.md` / `show harbour` / `search Alice` | Inspect Markdown without model calls. |
| `co rem status` / `sources` / `config` / `logs` / `logs --usage` / `doctor` | Inspect configuration, progress, diagnostics and reported usage. Status also reports Collect, Investigate, Deepen, Abstract and Translate in order, with waiting counts and last-run dates (or never); JSON uses `stages`. When the last night used its share of investigations, the Investigate line says so and how many pages wait for later nights. While pages wait for translation, the Translate line says how many a round translates at most (`limits.translations_per_round`). |
| `co rem open` | Open the live reader served by `co ai` on this computer, from the page saved at the last render, so it opens at once. When no `co ai` answers and a saved page exists, that page opens immediately while `co ai` starts in the background; the next `co rem open` is live. Only a `co ai` of the installed version serves the reader; see [Which server serves the reader](#which-server-serves-the-reader). |
| `co rem open --local` | Open the saved self-contained HTML page (a `file://` link, works offline). A notebook changed since that page was rendered still opens at once; a newer page is built behind it and the next open shows it. The very first open renders once, synchronously. |
| `co rem open --live` | Open the live view in O Chat, read from your `co ai` Host over OIP. Reuses an online Host or starts `co ai` automatically in the background, without channel listeners or an extra chat tab; the Host `co rem` started before an upgrade is replaced first. Opens live REM only after readiness; failure names `.co/rem-live-host.log` and labels the snapshot fallback. Default notebook only; `--no-launch` still starts the Host but only prints the URL. |
| `co rem open --no-launch` | Print the page without opening the browser. |

Run `co rem catchup` to do the night's work, including its one deepen slot. Use
`co rem catchup --nights 5` to run both five times back to back. `--nights` is
optional, defaults to 1 and must be at least 1. Each night uses `co rem exec`'s
existing round, which owns the same automatic slot as `co rem deepen`: one enrich
and muse round per selected page, using the default page count and
`limits.depth_workers`. It calls the configured model and reads sources up to
now. A night with deepen can take an hour or more: large-page rounds measured
35–97 minutes. The schedule is untouched. A notebook-local
counter gives it fresh daily and nightly limits; page dates, source windows
and scheduled due times stay real.
The Codex usage floor still stops the run. A spent weekly investigation budget
does not: investigation waits for the week's reset, the night's line says so,
and the night's other stages run.
Deepen keeps its separate weekly budget and the same quota and usage floors
as the scheduled slot. A spent deepen budget or no qualifying pages still
counts the night; the line says why no pages were deepened.
The daily investigation call cap leaves room for the same translation tail as
the scheduled round. Each line reports that night's mail and sessions read,
pages written and how many of them are decision pages ("81 pages written (66 of
them decisions)"; the two used to be listed side by side and read as a sum),
translations, drafts and pages deepened; totals follow. A productive night stopped at the daily cap keeps its counts and
can repeat with fresh limits; it has deepened if it got through its first
portion of investigation, and not otherwise, because its round is unfinished.
If exec is busy, reaches a quota floor or stops before the first portion, and
when a night with nothing to investigate produces no pages, translations or
drafts, catchup stops without starting deepen.
Saved work survives interruption, including during deepen.
A page whose enrich turn was refused or failed is not counted as deepened. It is
counted after it, with the first page's cause in a few words and no local path;
the full refusal is in `co rem logs`:

```text
Night 1: … · 2 pages deepened · 1 not deepened (enrich refused: Research captures need an HTTP(S) URL or a native read-only source ID; see co rem logs)
```

`--json` carries `not_deepened` and `not_deepened_reason` per night and in the totals.

A long investigation queue never keeps the rest of the night from running.
Once the night's share of investigations is used, the round goes on to its
other stages and the line says what waits, after the pages deepened:

```text
Night 1: … · 3 pages deepened · 12 of tonight's 12 investigations done; 319 wait for later nights · 3 of tonight's 3 skill pages done; 144 wait for later nights
```

`--json` carries the same numbers per night under `shares` (`investigations`
and `skill_pages`, each with `done`, `limit` and `waiting`). The next night
continues with the pages that waited.

When every page left in a round is parked, the round ends with that reason
(exit 1) and still saves the calendar and the day plan first, as every round
does.

One page never stops the night. When review refuses a candidate, exec (and so
catchup) runs that task again with the refusal as its required corrections.
An audit refusal names its findings under its first line, up to three, one
line each (`Finding 1 of 2 — claim: … | cited: <source id> | problem: … |
correction: …`); the task's instructions file lists up to five in full. Two
audit refusals are the same reason only when they fail the same claims: the
sentence above the findings is the same for every audit, so comparing it
parked a page whose second refusal was about something else (#3083).
One refusal is settled without parking. When the refusal that would park a
page names nothing but lost quotes or sources (`Dropped quote the page had`,
`Dropped source id the page had`), review puts the lines that cited them back
unchanged beside the rewrite and accepts the page, as enrich and muse do. The
repair before it asks for the sentence that cited each one, with its citation:
a Sources entry no sentence cites is removed again, so adding the id alone was
refused for the same ids until the page parked (2026-11-17). The submit says
how many lines came back, and the run record keeps the count
(`restored_lines`). A line the worker removed on purpose is back too: review
cannot tell a deliberate cut from a lost one. A page accepted this way has no
cited-claim audit; its `review.json` says `not automatically assessed`.
A source counts as one the page had only when a sentence of the old page
cites it. An id that was merely listed, or cited only inside a diagram, is
removed from every candidate as uncited, so no repair could keep it and the
restore had no line to bring back: a real run put 4 lines back and still
parked the page for one such id (2026-11-17). It is no longer refused.
The restore runs only when every error left is a dropped quote or source; a
refusal that also names another error (a capture's format, a quote not in its
source) is repaired by the worker and parked on the usual count.
A task refused twice for the same reason, or three times in all, is parked:
the reason goes to the refusal ledger (`.state/refused-investigations.json`),
the last candidate and its `review.json` stay in the task's folder under
`.state/tasks/`, the pending task is cleared and the round continues with its
next work. A parked page is not picked again in the same night and returns as
a retry on a later one (after 20 hours on the schedule), up to three retries
on the same material. A retry that is parked again in the same words, from the
same material, uses the retries that were left: the next night would buy the
same refusal. Out of retries, the page waits for new material, and its own
queue does not list it again either until mail or a session newer than its
last refusal arrives (it used to come straight back as an unfinished page, so
one page was parked six times in a day, #3083). The night's line and the totals say it:

```text
Night 1: … · 1 page parked (projects/fern.md: refused 3 times: the rewrite dropped 6 sources the page had; candidate kept at <root>/.state/tasks/native-<id>/candidate.md; co rem status lists them)
Done: 1 night · … · 1 page parked (projects/fern.md: refused 3 times: the rewrite dropped 6 sources the page had; candidates kept under <root>/.state/tasks; co rem status lists them)
```

A night that parked several pages counts them by cause instead of naming one
page: the most frequent cause first, three causes at most, then how many more
(it printed only the first page's cause, 2026-11-17):

```text
Night 1: … · 2 pages parked (1 page, refused 3 times: the rewrite dropped 6 sources the page had; 1 page, co ai timed out after 1200s; first candidate kept at <root>/.state/tasks/native-<id>/candidate.md; co rem status lists them)
```

The parenthesis carries a short cause, not the stored reason: how often the
page was refused, then one clause. A rewrite that dropped what the page had is
counted (`the rewrite dropped 6 sources and 1 quote the page had`); any other
cause is its first clause (`Quote is not in its cited source`, `co ai timed out
after 1200s`), with no source ids and no local paths. The stored reason is cut
at 300 characters, and on 2026-11-17 the line printed that: a list of source
ids ending mid-word. `co rem status` still lists the whole reason. A candidate
is named only while its file exists (`no candidate is kept` otherwise): a
parked task keeps `candidate.md` and its reviews, while investigation notes or
a translation go with the task's material, and the line had named such a path
after it was removed.

`--json` carries the same rows in `parked` (`record`, `why`, `cause`,
`candidate`) per night and in total. Parking is not a failure: a night that parked pages exits
0, as a night stopped at a limit does. A task that an earlier stopped run left
pending is resumed by the next catchup or `co rem exec` through the same
retry-then-park path; only a task another live process is working on stops
the night (exit 1, with `co rem next --discard` named). `co rem submit` and
`co rem next --discard` still work by hand.

A page whose first investigation pass was accepted before a night ended keeps
that draft into the next night and goes on to its remaining pass. A page that
changed meanwhile is investigated again from the start, with one exception:
when the only change is the contact script's own (First contact, Last contact,
company and time zone filled from the mail index), the same script is applied
to the draft and the page resumes. Before, that rewrite alone restarted a
person's page at its first pass: 2,158 s and 10.75M tokens over three turns on
2026-11-16 (#3083). An edit by you, or by a turn that read new mail, still
restarts the page.

The same holds for a task exec cannot settle. Its instructions print the
submit command, and the worker may run it itself: exec then reports what that
submit recorded (accepted, or parked after its refusals) instead of submitting
a task that is no longer pending, and takes the task the worker's own
`co rem next` prepared. The worker is not asked to run one: a task exec hands
out is marked `driven` in its `task.json`, and a submit of it ends on `Next:
End your turn: the co rem exec that started this task takes the next one.`
(`"next": null` and `"driven": true` with `--json`), never on `run co rem
next now (same turn)` and never with the scheduled agent's "keep going until
the round is done". A parked submit printed that line to exec's one-task
worker; it obeyed, and the task it prepared waited 7,383 s for a driver
(#3083). A driven stage that the harness confines to its task folder
(every stage but investigation and init, with the Codex or Claude Code
runner) is also not told to write outside it: its instructions leave out the
`.state/memory.md` step, and its claim audit ends "end your turn: the run
that started this task submits it" instead of "run next again … run the
printed Submit command", with the audit's `Now:` batch added to the prompt
exec hands it. Both commands take the notebook's lock, which is outside the
folder: 76 tool outputs in one day were permission errors, 58 on that lock.
The repair of a refused page follows the same rule: its `## Required
corrections` end "end your turn: the run that started this task submits it.
Do not run co rem submit; this sandbox refuses it." instead of "Run co rem …
submit again in this turn". The investigation Skill asks for the memory lines
only "when the task instructions name a memory path".
A repair runs in its stage's sandbox, and one rule decides both the flags and
the wording: exec names a repair `investigate (repair)`, the flags used to
take that for a confined stage while the wording did not, so a
`workspace-write` investigation repair was told to run submit (3 permission
errors in one repair, #3083). An investigation's repair now has the access its
first pass had and submits its own page; a maintenance or translation repair
stays confined and ends its turn. The corrections are also rewritten when the
task changes hands: a page refused under `co rem next` and offered again by
`co rem exec` (or the reverse) gets the ending for the worker that now has it.
A task's inputs include `config.yaml`, read for what shapes its material only:
the evidence-sizing limits (`items_per_batch`, `input_chars_per_batch`,
`extract_items_per_batch`, `extract_chars_per_batch`, `investigation_rounds`)
count, and the limits that bound future work (the daily call cap, the nightly
shares `investigations_per_night`, `skill_pages_per_night` and
`abstract_rounds_per_night`, workers, timeouts and budgets) do not. A task
prepared before `abstract_rounds_per_night` existed was parked as changed by
the release that added it (2026-11-17); every default limit is now named in
one of the two groups, and a test fails for one that is not.
A task whose inputs changed while the worker ran, one
that is no longer the round's pending task, and a turn that passes
`limits.timeout_seconds` are parked with that error in words, listed like any
parked page, and the round goes on. The parked task's record keeps the tokens
its turns used: what a timed-out turn reported before it was closed, and the
whole turn of a task whose submit then failed (it recorded none, 2026-11-17).
Two such tasks in a row stop the round
instead (`2 tasks in a row could not be run, so the round stopped; the last:
…`), so a dead network does not park every page for a day.

A page whose preparation passes the ten-minute `co rem next` deadline inside
`co rem exec` or `co rem catchup` is one such task. The deadline interrupts
the preparation where it waits (a folder listing held by a macOS privacy
prompt is interrupted too), the notebook's lock is released, the page is
parked by name (`parked: preparing it passed the 10-minute deadline while
searching project documents`), exec prints `Parked <page>: …` for it, and the
round prepares the next page in the same process. It counts towards the two
in a row. Only a preparation that does not stop within 30 seconds of being
interrupted still ends the process with exit 75, as a single `co rem next`
does; catchup first prints the night's line and `Done:` with `Stopped: co rem
next passed its deadline while <step> and could not be interrupted`, so a
night never ends without its totals. The page is parked by the next
`co rem next`, exec or catchup.

What stops the round is what is about the round, not one page: the runner
cannot start or does not complete (a refused model, a spent provider limit),
the notebook's lock is held by another process, the notebook cannot be read.
Catchup then still prints the night's line and the totals, with the reason in
words on both and on `Stopped:`, exits 1 and starts no further night:

```text
Night 1: … · 1 pages written · … · 0 pages deepened (exec stopped: co ai did not complete (exit 1, outcome missing): usage limit reached) · 1 page parked (…)
Done: 1 night · 1 pages written · … · 0 pages deepened (exec stopped: co ai did not complete (exit 1, outcome missing): usage limit reached) · 1 page parked (…)
Stopped: co ai did not complete (exit 1, outcome missing): usage limit reached
```

A night in which a task was parked for its own error is a night that ran: the
next night of `--nights N` starts as usual.

When the Codex usage floor already holds the
model before the first night, catchup does not print an empty night. It does the
steps that call no model, once, and spends no night:

- **Collect**: reads new mail and coding sessions into the round, as far as the
  scheduled turn does before its first model task. The scheduled turn then lets
  the model read that mail into pages even under the floor (bounded by the daily
  call cap); catchup stops before that, and the next turn that may call the
  model reads the same batch without fetching it again. A batch already waiting
  is kept, not fetched twice; a round already open with its batch read gets the
  mailboxes read into it, and the line then counts mail only.
- **Calendar**: saves the upcoming events and the day plan, as every round does.
- **Investigate, Deepen, Abstract, Translate** wait: they call the model.

```text
No night ran: a limit holds the model, so only the steps that need no model were done.
Collect: 2 mail collected · 0 sessions read · 0 pages updated; reading them into pages waits for the model
Calendar: 0 calendar events saved · day plan saved for 2026-09-07 and 2026-09-08
Waiting: Investigate, Deepen, Abstract and Translate call the model
Stopped: the Codex week is at 99%, at or past the 90% floor kept for your own work; investigation resumes when it resets Wed 09 Sep 22:00
```

`--json`
carries the same under `held` (`note`, `mail`, `sessions`, `written`, `calendar`,
`day_plan`, `waiting`, `resumes_at`); `held` is `null` when a night ran. The
exit code is 0, as for every stop at a limit (`co rem exec`, `co rem
investigate`): nothing is wrong and nothing needs repair. Exit 1 means a
refused or busy task, or a round that failed.

Run `co rem decisions` to see how many decision and principle pages exist and how
many supported captured lines are waiting. Waiting and left count only lines
with a verbatim quote and a bound original source, excluding captures contradicted
by stored owner input. Status and the final write summary separately count captures
with no quote, no bound source, contradicted owner words, or judged not a decision; these totals count
each line once across the notebook, rather than accumulating across rounds.
Legacy session pages list unnumbered sources: a quote receives a numbered binding
only when its words and captured clock identify one retained owner turn on that
page. Ambiguous or unmatched quotes stay out of the packet. No original transcripts
are added to the model's material, and the session page remains unchanged.
Run `co rem abstract` to write supported captures
now, oldest first, up to 20 decision lines and 20 reviewed pages per round. Each
round calls the existing configured model runner once and uses the same material,
input character bound, owner-quote and citation checks, and decisions/knowledge/principles
write scope as the night. Passing pages are kept; refused pages and reasons are
printed and saved with the run. Each decision copies the owner's quote exactly as
captured in the supplied Decisions or Key decisions into the body immediately
followed by its `[n]`; `## Sources` defines the original source ID for that number
and ends with `— originating page: <path>` (the task's example line now shows it;
it ended at the source ID and no page of that night kept the path). A quote
placed only under Sources is refused with instructions to move it into the body.
The page limit is a ceiling: zero pages is valid. Never turn a paraphrase into an owner quote. A quote too long
for the input bound stays pending, rather than being split into unusable fragments.
Each offered line has a stable short ID. A passing page that quotes it counts as
written. For every line it does not quote, the model reports either a merge into a
decision page it wrote this round, or not a decision because no alternative was
rejected, or because the pages do not say which alternative or why. A decision page
whose own text says its alternative or reason is unknown or inferred is refused,
and the refusal asks for the not-a-decision verdict instead (15 of 66 pages of
one night said so and had passed). A merge finishes only when the named page passes review. Merged lines
and lines judged not a decision are done and never retried. Verdicts for IDs outside
the packet are ignored. Refused lines keep the check's reason; lines with neither a
page nor a verdict count as no answer. Both retry up to three attempts.
A round that resolves no lines counts as an empty round, sets its slice aside for
a later retry, and moves to the next slice. It continues until nothing unattempted
is left or two empty rounds occur in a row; a written, merged or not-a-decision
outcome resets that streak.
`--rounds 2` stops after at most two rounds. Output gives per-round counts and
totals, slices set aside for a later retry, captured lines left, then `co rem list decisions`.
The result and the Abstract line in `co rem status` report decision, knowledge
and principle page counts separately. `co rem decisions` keeps its existing view.

The lifts run in order: **decisions, knowledge, principles**. Abstract knowledge
records learning that holds beyond one choice: how something works, what went
wrong and why, or a method that worked. Each `knowledge/` page names at least two
notebook pages from `decisions/`, `sessions/` or `projects/` under `## Drawn from`.
It keeps the same verbatim body quote, immediate `[n]`, original source ID and
originating-page citation rule as decisions. This is learning from notebook
experience; Investigate topic pages describe a subject from raw sources.
Abstract may create knowledge pages or add clearly headed sections to existing
ones, including Investigate pages; it must preserve all existing text exactly.
**A knowledge page ends with one `## Sources`** (#3097). When the page already
ends with its `## Sources`, the new section goes above it with its own
`### Drawn from`, and its source definitions are added to the end of that one
list, continuing its numbers. Only a page with text after its `## Sources` (an
Investigate topic page with its stamp, or a page written before this rule) still
takes the section at the end with its own `### Sources` and fresh citation
numbers; existing pages are not rewritten, and the reader gathers both shapes
into one list.
Knowledge passes the same promotion/review path and joins translation discovery
alongside decisions and principles.
Translation includes appended experience while preserving every source definition
and the original investigation stamp. The Knowledge reader shows settled learning
and its Drawn from links alongside any existing topic content.
Status and the final summary show line totals separately: written, merged,
refused, no answer, and given up. Skipped includes not a decision. Refused and
no-answer totals include given-up lines; waiting and to retry exclude them.
These saved totals count each current captured line once, across runs.
Exit is 0 after progress (including verdicts) or when nothing is waiting; it is 1
when no attempted round resolves a line, with the reason on the last line.
A crash leaves its captured lines pending.
Manual success shares the night's saved progress, so neither repeats the other's work.
A manual attempt neither uses nor consumes `limits.abstract_rounds_per_night`;
each failed manual run counts once for that slice toward the existing three-failure
rule, as does each distinct failed night. After three failures the queue releases
the line and records the reason. Old receipts without verdicts retain their failure
history and get one more offer, including lines previously given up, so the model
can give a verdict. Successes after a failed gap are saved separately
so the gap can retry without repeating later successes. `co rem abstract` is the stage 4 command.

Quote equality with a captured line does not prove who said it. Before promotion,
the manual and nightly abstract check local stored originals, without fetching a
source or handing raw messages to the model. A quote found in another sender's
own mail body or an assistant reply is refused as not authored by the owner.
A quote absent from its complete cited original is also refused. Typed session
input and the owner's own mail body can establish owner authorship; quoted mail
history cannot inherit the sender's identity. Missing or truncated originals,
unknown senders, and file, repository or web sources leave the speaker unverified.
Such pages use the existing `## Uncertainties` section with one line:
`- Speaker unverified.` No speaker is guessed from wording or a citation prefix.

After session summaries, the night runs successive abstract slices when session `## Decisions`
or project `## Key decisions` contains new or changed captured material. Oldest sections are offered first,
with at most 20 nonempty decision lines per packet (large sections continue on later
slices), within the configured input character budget and with only sources bound
to their quotes. Each completed slice admits the next, setting an empty slice aside,
up to `limits.abstract_rounds_per_night` (default 6). A backlog of N decision lines
takes roughly ceil(N / 20 / rounds) nights, where rounds is that nightly limit,
or longer when slices fail or the character budget requires smaller packets. Section hashes
advance only over successful or released slices; later successes are saved beyond
any failed gap. Empty slices retry on a later night or manual run. After three
distinct failed nights/manual runs, a slice is released and its offsets, failure
attempt IDs and give-up reason are saved in abstract-offered.json.
A crashed turn leaves its material pending. It writes or updates at
most 20 pages under `decisions/`, `knowledge/` and `principles/` only, with the owner's words
and original citations on each decision. Assistant proposals without the owner's
acceptance are excluded. Principles still need at least three decisions. The saved
night marker counts reserved rounds in the notebook’s noon-to-noon night, so a restart
keeps the count, attempted slices and consecutive empty count; the next night starts
at zero. An unfinished reservation blocks new slices until its outcome is recorded.
Two rounds in a row with neither passing pages nor completed line verdicts stop
new abstract slices for that night. The later
same-person and translation passes follow at most six abstract rounds by default.
Passing pages are saved; rejected
pages and their errors are recorded in the run. A task with no passing pages
fails. With no unoffered material, this stage makes no model call.

`co rem show NAME` searches people, projects, orgs and skills. An exact page
path wins; otherwise it matches page titles, page stems and project folder
names case-insensitively. For example, `co rem show harbour` can read
`projects/harbour-<hash>.md` whose Paths section lists a folder named `harbour`.
Person aliases and email addresses keep working, as does `co rem show me`.
Several matches produce a list of paths and show no page; pass one exact path
to choose. A missing name reports the searched name and page kinds.

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

Native scheduled rounds investigate pages before summarising sessions, with at
most five summaries per round. Unwritten people, projects and other mapped
pages stay in the scheduled queues until processed; your own page refresh is
queued each day. Status and the reader show queued progress instead of asking
you to copy a REM command for that work. A round takes every queued page; `limits.runner_calls_per_day` (default 200)
is set in `config.yaml` or with `co rem config set limits.runner_calls_per_day 200`.
The weekly quota safety floor remains 90% by default.

Intermediate native investigation rounds keep private candidates. One final
claim audit gates page promotion; its packet omits sentences whose wording and
citations were carried unchanged from the page before the task. Editing an
unrelated notebook page does not invalidate a prepared task.

A native project candidate left unchanged while its material contains inputs
newer than the page's `written_through` is refused: the new inputs must be read.
To record an intentional no-change assessment, write `NO CHANGE: <reason>` in
the task's `report.md`. An unchanged assessment does not advance input coverage;
an accepted changed page advances only through the inputs supplied to it.
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
Unresolved `git:` citations are read from the local checkout with `git show`, capped at 40,000 characters.
The critic judges the same packet twice independently, keeps only bullets both calls rate good, and records both verdicts and their disagreement count.
Only good insights are kept; weak or wrong bullets are removed, and a weak finding about an obligation
or a question still owed can move to Open threads.

A study turn adds a bullet only when its verdict is insight, and `Insight`
keeps at most four: the turn text said "Add a new bullet" in each of the five
study turns, which asked for five and for one from a question that yields
none. Five is the number of questions, four the page's limit; a fifth names
the weakest bullet it supersedes and leaves replacement to the reviewer.

A web page that enrich or muse cites needs a saved capture, as in
investigation: the turn is told to save the text with `co fetch <url> >
<task>/web/<slug>.md` and register it in `<task>/web/sources.json`, or not to
cite the URL. A page refused with "Web citation needs a saved capture in
web/sources.json" goes back with that remedy (save the cited page and
register it, or remove the citation and any claim resting on it alone). On
2026-11-16 a muse run with five insights rated good was refused for this, and
neither the Skill nor the repair text said what a capture was (#3083).

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
`co rem exec` and the `python -m connectonion.rem.codex_exec` launcher also
run the same slot after a completed whole round. Their closing
translation has already run; deepen changes await the next translation pass.
Catchup reuses exec's slot and reports its results without calling it again.
`co rem exec` retries a refused candidate and then parks it as catchup does,
and prints one `Parked <page>: <reason>` line for each.
In-session `co rem next` / `co rem submit` does not deepen. Early stops and
translation-only exec rounds skip the slot.

### What the reader shows

Opening is a file read. The reader keeps its last render outside the notebook,
in a private per-user folder in the temporary directory (`co-rem-cache-<uid>`,
mode 700, pages 600, a planted link refused), and serves it at once. Whether it
is current is a handful of stat calls, never a listing of the notebook: every
write REM makes touches `.state/reader-changed`; the category folders' times
catch a page added, renamed or removed by hand; `.state/rem.db` and a nonempty
WAL hold committed rows; `reader.html` and the installed version are part of
the key, so an upgrade re-renders. The version is read from the installed files
(`_version.py`), not from the running process: a Host started before an upgrade
kept the old version in memory, never matched the pages the build saved, and
showed **Updating…** on every page for as long as it ran. The notebook's date is part of the key too, so the Today queue turns
over at midnight. Every 10 minutes (`REBUILD_INTERVAL` in `reader.py`) the
background build walks the whole notebook (on a 31,136-file notebook about
17 s of stat calls, never on the request path), which catches edits other
tools make in place without REM's writers, and rebuilds only if the walk
differs. The walk leaves out the lock's own files (`maintenance-owner.json`,
`maintenance.lock`), which the Host's minute tick rewrites, and the marker;
otherwise every walk would differ while a Host runs. A page older than an hour (`STALE_SCHEDULE_SECONDS`) is rebuilt
anyway, so **Next pass** and schedule text are at most an hour late; a quiet
notebook with the page open costs a walk every 10 minutes, not a rebuild.
When the key changed, the last page is still served at once and one detached process
(`python -m connectonion.rem.reader`, one at a time, log in the same folder,
trimmed to its last 200 lines) renders the new one. It writes the new page,
details and file page under new names, then one manifest (`current.json`) that
names that set, last; a crash midway leaves the previous set served whole, so a
reload never pairs a new page with old details. The set it replaces is kept for
a page still open on it. The offline page keeps one name per notebook
(`<digest>-file.html` in the cache folder), replaced in place by each build, so
the link `co rem open` prints stays valid and a tab open on it shows the newest
render when reloaded. When the notebook's last render took under 2 seconds
(`SYNC_RENDER_SECONDS`), an explicit `co rem open` renders it again before
opening, so the page is never older than the notebook; a larger notebook opens
the saved page at once and is rebuilt behind it. `CONNECTONION_REM_CACHE`
names another cache folder; the test suite gives each test its own and fails a
run that writes the real one.

Rebuilds are at most one per 10 minutes, because one costs about 100 s of CPU
on a large notebook and a night run keeps writing. The owner acting rebuilds
at once: an explicit `co rem open`, and a change made in the reader (send,
approve, mark a thread, choose a language, `/rem/translation-request`, stop or
undo a task). Reading a task's status, and the on-page translation
(`/rem/translate`, served straight from its own cache), do not. A build that
is running passes again for an owner action made meanwhile. `co rem open` says
a newer page is being built only when a build actually started.

The open live page asks `/rem/version` every 30 seconds while visible. When a
newer render has landed (only newer: an equal or older time is no reason) it
reloads onto it and puts back the view, the scroll position and open sections
(known by id, else by their heading); while you are typing it waits, and over a reply
you have edited it does not reload but shows a quiet **有更新 · 刷新** (Newer
page · Reload) link. After Stop or Undo on a task, the page waits for the
render that carries it, then reloads; past two minutes it says the page has not
updated yet. Refresh task progress reads the status in place.

The footer says when the page was rendered: **Updated** (更新于) and the time.
If the newest background build failed it adds "the newest rebuild failed", with
the log path as a detail; `co rem open` says the same. A failing build is not
started again within 10 minutes. If the cache folder exists but is not yours
alone (a shared temporary directory), the reader renders now, as before saved
pages, and says so; a Host that `co rem open` started and that exited soon
after is named with its log, `rem-live-host.log`, on the next open. Before this (1.9.3rc62) every open
rebuilt the whole notebook: on a 31,136-file notebook the key alone took 17 s
and the render 35 s, plus 73 s for the details.

### Which server serves the reader

`co rem open` reads through a `co ai` on this computer. It asks the port it
started one on last time (kept in `rem-live-host.json` in the identity folder),
then `co ai`'s default port 8000, and uses the first whose `/info` gives your
address **and the installed version**. A `co ai` you run by hand on port 8000
at the installed version is used as before.

A `co ai` keeps running the version it was started with, so after an upgrade:

- **The one `co rem` started** is stopped and a new one is started on the same
  port. It is that one only when the pid in `rem-live-host.json` is your process
  with the recorded command, and the record's `install` (the connectonion package
  folder that started it) is this one's, so another install sharing this home
  never takes it for its own. A record from before `install` existed (1.9.5) is
  matched by the full command line `ps` shows, interpreter included: that works
  for a uv tool or a venv; on a macOS framework Python (Homebrew, python.org)
  `ps` shows the binary inside `Python.app`, so that old Host is reported, not
  replaced. `co rem open` and
  `co rem open --live` do this when you run them. With a saved page, that page
  opens at once and the next open is live.
- **A tab that was already open** needs no command. Its reload asks the old
  server, which starts the usual background page build; the build is the
  installed version, and when it has saved the pages it replaces that server on
  the same port, so the tab's address and link stay good and the page reloads
  onto the new render. A task started from the reader runs in its own process
  and continues. An identity selected with `--env-file` is replaced by the next
  `co rem open`, not by the build.
- **Not while it is working.** Neither an open nor the build stops it while
  `session_results.jsonl` holds a turn still `running` or `waiting_approval`
  (a conversation, an approval being waited for, or a scheduled `run:` turn) or
  `schedule-state.json` marks a scheduled `exec:` command `running`, nor when
  the open is itself run from a turn inside it. The open shows the saved page
  and says the server from before the upgrade is finishing a task. No age makes
  such a record stale: a Host marks every earlier Host's unfinished work
  interrupted or failed when it starts, so what is unfinished is the running
  Host's, an approval waiting overnight included.
- **Any other `co ai`** of another version that answers as you on port 8000 or
  the recorded port, including another install's, is not used, never signalled,
  and no Host is started beside it, because a second Host on one identity folder
  marks the first one's turns interrupted. The saved page opens with one line
  naming its port and version; live actions return when that `co ai` is closed.

Limits, one each:

- A Host is replaced at most once per installed version (as `co <provider>
  listen` restarts, #1878): `python -m` run inside a checkout of another
  version imports that checkout, so a replacement started from there comes up
  at the other version again, and the open then says so instead of retrying.
  The mark (`renewed_for`) is in the replacement's own record, so any later
  launch clears it.
- If the new Host exits before it answers (its port was taken between the check
  and its bind, or it failed to start), the open or the build starts it once
  more on a free port and the record names it; a tab already open gets no answer
  until the next `co rem open` prints the new address. A new Host that is slow
  but running is not moved.
- A `co ai` of another version on a port other than 8000 or the recorded one
  is not seen at all.
- On Windows there is no `ps` to prove a pid is still our Host, so a Host of
  another version is only reported, never replaced (`live_host._started_here`).
- A busy Host from before the upgrade keeps serving until its work ends, however
  long that is.

The reader returns the context REM carried forward. It remains a point-in-time snapshot.
When pages already exist but no background schedule is authorized, its status
says **Background updates off** and offers `co rem start`; the written pages
remain available. A wholly empty notebook still says **Not started**.
The foot of the rail holds **Settings** and your own face. **Settings** opens one
sheet: **EN · 中文**, **Auto · Light · Dark**, Reduce motion, Hide labelled
passages, the notebook's languages, REM's state in words, the legend, and last
the release (**co 1.9.3**, read from the installed package and the same in both
languages) with the snapshot time and **Keyboard shortcuts**. The primary
language control is the one-click button at the top right of every page (in the
phone header too): it names the language it switches to (**EN** while in
Chinese, **中** while in English), saves the same choice as **EN · 中文**, and
redraws in place, keeping scroll and open sections. Words you are typing stay
too, with the caret and the focus: an answer slot in a reply, the chat box, an
approval's reply body, a review answer. If a field holds words the page could
not put back after a redraw (an answer slot of a reply that has no id), the
click does not draw over them: the button flips, the choice is saved, **有更新**
shows, and the page changes language once those words are sent or cleared and
you have left the field, with the sections open then kept open. Status and privacy controls live under it in **Reader settings**. **EN · 中文** switches
interface labels and dates. Your saved choice comes first; otherwise Chinese when it is
your language (the rule drafts and the night's translation use too, under Writing
languages), or when your language is one the interface lacks and Chinese is among yours,
then a Chinese browser language, then English.
Older notebooks without saved language detection read your own sent mail and
typed sessions on opening, without writing to the notebook. Configured
languages still take precedence. Page prose stays as written. On phones the sidebar's places sit in a floating tab bar at the bottom edge
(Today, Waiting, People, Search, More); **More** opens every place as a sheet, in the rail's order. Today's Send is not
pinned to that edge: it comes into view with the draft.

- **Home** is a morning brief, read top to bottom. A date line and one
  sentence count what matters ("1 change overnight · 1 overdue · 1 due soon · 4 waiting
  on you"); a quiet line under it summarises the last pass, with its
  hypnogram one click away in **How co rem processed the last pass**.
  Overdue and due-soon counts are separate. First-build wording uses the
  notebook's earliest run, even when only recent runs fit in the snapshot.
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
- **Today's order, and what every action does** (since sprint 22, #3072, #3085;
  this replaces the order described under **Your day** and **To-dos** below).
  Today opens on what can be acted on and ends on what is only read:
  1. the count of things waiting on you and the faces of who waits;
  2. **work in hand**, one line, only while there is some (see below);
  3. the deck of cards, one in front, with **Waiting on others** at its side;
  4. **N have gone quiet for a long time · Look**;
  5. **Finished today: N** and **Put off: N**;
  6. **To-dos** (your Microsoft To Do tasks, which have no buttons here);
  7. **Your day** (calendar events and the proposed half hours);
  8. the folds (overnight changes, pages rewritten, how the last pass ran).

  **Every action on a card moves on.** Mark done, Not now, Ignore, Send and
  Hand to Codex / Claude all take the item off the deck at the click, and the
  card that followed it comes forward. When the card still has other rows for
  the same person it stays in front with the next row moved up; it is never
  the first card dealt again (before sprint 22 the deck went back to its first
  card after any close, which is what "it goes back to that thing" was). The
  page keeps its scroll position through the click and through the save that
  follows it. The item leaves every list at the same moment: its card, its
  proposed half hour under **Your day**, and its row in **Waiting on you**.

  **One number.** The header's count, the rail badge and the phone tab's badge
  are the same number: the items in **Waiting on you**'s first band (you owe
  them, not quiet, not asked about as long-silent, not answered by a reply held
  or sent). It changes with the click. Every other number on the page says in
  words what it counts: *See the N waiting on others*, *N have gone quiet for a
  long time*, *Finished today: N*, *Put off: N*, *Codex is working on N things*.
  The deck deals the most pressing few; when it holds fewer items than the
  count, a line under it says so (*These cards are the most pressing 5 of the
  59 waiting on you. See all 59 →*).

  **Done, and undoing it.** After a close the notice says what happened, in
  words, with **Undo** and then the list that now holds the item: *Marked done ·
  Undo · Saved in notebook · Finished today: 3*. The notice leaves after five
  seconds; the list stays. **Finished today: N** (今天已完成：N) is a fold under
  the deck holding what you marked done or ignored on this calendar day (the
  reader's local day), each row with **Bring back** (放回去), which reopens it
  and puts its card in front. The fold empties at midnight. Nothing is deleted
  then: an item finished earlier stays in the closed list at the foot of
  **Waiting on you** (*Marked done · Ignored (N)*) for as long as its line is on
  its page, and in its own page's history, and **Undo** works in both.

  **Not now asks when** (暂不处理). It used to have no date: the item left
  Today and came back only when new mail arrived on its thread, and after the
  notice left nothing on the page said so. Now the strip turns into *Bring it
  back: Tonight · Tomorrow · In 3 days · Next week · Cancel* (什么时候再看：今晚 ·
  明天 · 3 天后 · 下周). Tonight is 18:00 and is not offered after it; Tomorrow and
  In 3 days are the start of that day; Next week is the coming Monday. The
  notice then says *Put off · back on Thu, Nov 19 · Undo* (*back tonight at
  18:00* for Tonight). **Put off: N** (已推后：N), beside Finished today, lists
  every item put off and not yet back, whenever it was put off, each saying
  when it returns and each with **Bring back now** (现在放回去). New mail on the
  thread still brings an item back sooner. When its time comes the card is back
  in Today by itself, on a page left open and in the next night's list alike,
  and says *You put this off on Nov 17; it is back as you asked.* (or *…new
  mail brought it back.*). The mark is `/rem/thread` with state `skipped` and
  `until`, an ISO moment, kept in `.state/threads.json` beside `at`, the moment
  it was put off; `threads.listing` reports it returned once `until` has
  passed. A draft's **Skip** and a mark without `until` behave as before
  (*Not now · returns with new mail*). A draft set aside by a put-off is not
  restored when the date arrives; the card returns without it.

  **Work in hand** is one line above the deck, shown only while an agent holds
  something or finished something today: *Codex is working on 1 thing · started
  2 min ago*, *Handing 1 thing to Claude…*, *Codex finished 2 things*, *Codex
  stopped before finishing 1 thing*. It opens to the rows: the item, what the
  agent is doing and since when, **Stop** and **Take back from Codex** while it
  runs, then **See result**, **Show its card** and **Take back**. It is read
  from the same receipts the rows carry (`.state/tasks/do-<id>/receipt.json`);
  there is no second store. The card of a row an agent is working on is out of
  the deck until the run ends; the count still includes it, and this line says
  so. **Hand to Codex** no longer waits for the Host before moving on: the row
  is the agent's from the click, and if the Host refuses, the card comes back in
  front and says why in red (*Codex did not take this: REM is not answering
  right now. Try again in a moment.*). A page that can no longer reach REM at
  all says *nothing was handed over. Open REM again and act from the page it
  opens.* In a snapshot the buttons are disabled, as before, and the card says
  *This is an offline snapshot; open REM to mark it.* with **Open the live
  reader** when this computer has one. The page never prints a command to copy
  (D-60), so it says *open REM* and not `co rem open`. In **Waiting on you**
  and the folds a hand-off is still said on the row, in place. A reply inside
  its ten-minute hold keeps its own line at the top of the deck (*Sent to … ·
  Held until … · Undo*), not in this strip.

  **Show more** (更多背景) is the last control of every row's strip, where
  **More ▾** was: *Mark done · Not now · Ignore · Hand to Codex · Hand to
  Claude · Show more*, the row's lead still in bold. It opens the item's second
  level without leaving the card: a panel at the right of a wide page, a sheet
  from the foot of a phone. It holds **Why it is here** (the whole line, its
  due date and since when the person has waited, and the put-off note),
  **The message** (who wrote it, when, its subject and the excerpt the page
  already carries; a passage labelled personal or sensitive is not shown),
  **Related** (the person, their organisation, the project, any other page
  the item is also on, and the mail thread) and **Talk it over** (With Codex,
  With Claude), which used to be the only thing under More. No model is
  called. Closing it (the cross, Escape, or a tap outside) returns the focus to
  **Show more** on the same card; a link or a talk choice closes it too.

  **In Chinese.** Every label, button and sentence the reader writes on Today
  follows the chosen language. An item's own words come from the **Open
  threads** line of its page, written at night in English; when the page has a
  current translation in the reader's language, the card, its proposed half
  hour and its rows in Finished today, Put off and work in hand show that
  line's translation. Until sprint 22 they did not: only a page opened with its
  own language switch showed translated lines, so Today stayed English on
  translated pages. A page with no translation yet shows its original line,
  marked **原文**; nothing is translated in the browser. The night already
  translates the pages behind Today's rows first (`translate.shown_today`,
  eight a night).

  **Waiting on you has filters** (#3072). A row of chips sits above the list,
  each a tag in words with its count; one tap filters, a second tap (or **All**)
  clears, and the filter rides the address (`#view=open&tag=…`). Pages carry no
  tags of their own yet, so the chips come from what each row already knows:
  two states, **I still owe a reply or an action** and **I replied, waiting on
  them** (the night's reply state for the row: your mail is the thread's last
  word and it reads as an answer), then places with more than one row: the
  person's organisation, an organisation's own page, a project. With a filter
  on, each band's heading counts the rows under it, and one line offers
  **Mark all N done** and **Put all N off until…** for every row shown. Neither
  asks anything more. Each row is its own mark in the notebook, and the one
  notice (*14 marked done · Undo · Saved in notebook*) carries one **Undo** for
  the whole batch. On a phone the chips are one row that scrolls sideways.
- **Today is one queue**: everything that needs you, newest and due first, one card
  each, with one primary action per card and a quiet **Mark done** saved in the
  notebook. Its cards lead with what you owe; their overdue chips and the faces'
  day counts use only your debts. What someone else owes stays under **Waiting
  on others**, even when overdue, and never takes a place in this queue.
  Done threads stay out of both night-run draft queues. The schedule prepares one local reply draft per mail thread
  waiting on you, with no nightly count (D-104), and every failed item named in status. Missing originals are fetched
  from already-consented mailboxes. Owner-last answers and promised work receive
  [morning outcomes](../rem-night-outcomes.md). Drafts use the `rem-reply-draft` skill: it reads who you both are (your page, their page,
  the relationship, how they write), decides on each ask in the latest message, and
  writes in your register for that relationship, using your own `email-writing`
  skill when one is installed under `~/.claude`, `~/.codex`, `~/.cursor` or `~/.co`.
  A prepared reply is shown as the mail it becomes: recipient, subject, the body in
  the thread's language, a gist in your language, and **Why this reply** (who they
  are, what was agreed, what you owe and since when). **Send** replies in the thread
  from your mailbox; **Write full screen** opens the letter to edit by hand, with
  that background and the thread beside it, and sends your edited text; **Edit in
  Gmail/Outlook drafts** creates an unsent provider draft; **Not now** keeps it
  out of Today until new mail arrives, when it returns with the new message date.
  Done and Not now offer **Undo** for five seconds; the record page keeps Undo
  available later, including a collapsed history if the original thread text
  has changed. Skipping preserves the draft body. The live reader shares these
  decisions through `.state/threads.json`. A mark tells the notebook only which
  mail it cites and the version the page showed, so what it sends stays the
  same size however large the notebook grows. If the notebook cannot be
  reached, is busy with another write (409) or the Host fails (5xx), the mark
  waits in localStorage ("Saved on this device — sync pending") and is sent
  again on load, focus or reconnection, with the mail versions it was made
  with, so mail that arrived while it waited still brings a Skip back. Any
  other answer is a refusal, such as a thread the notebook no longer has
  (400): the page goes back to what the notebook holds and the notice reads
  **Not saved** with **Try again** for the same five seconds; nothing is left
  waiting. If you have marked another thread since, its notice keeps its Undo
  and gains the **Not saved** line. The channel switch (Mail / Lark / WhatsApp)
  rewrites the reply for that channel and sends it as you through `lark-cli` or
  `co whatsapp`, when the notebook knows how to reach the person there. Sending
  and rewriting work in the live reader on this computer only; a click is the
  approval, and nothing is sent without one. Labelled private material stays
  behind the reader's privacy toggle.
- **Today is drawn as a fuse** (owner, 2026-11-09, D-108): the count of people
  waiting is the page's one large number, with the most urgent person named
  beside it (or, when nothing is overdue, whoever is first in line). Under it,
  one lane per waiting person, in REM's urgency order: a line from their oldest
  dated message to today, red for exactly the days past the due date. An item
  with no due date has no red and says **No due date**. A row on your own page
  belongs to the person it names (who asked, or who is owed); a row that names
  nobody is your own note and is not counted as a person waiting, in the
  headline, the lanes or the overnight names. Since sprint 14 the large number
  is the one "waiting on you" count, the same as the sidebar's (and the phone
  tab's) **Waiting on you** badge: the items in Waiting on you that need you
  (**21 things waiting on you**, 21 件在等你), and the rows of that band on Waiting on you are exactly
  those items: a reply sent or held for its 10 minutes leaves all three together (the hold's **Undo** bar shows on
  Waiting on you too), and with none waiting the header says *Nobody is waiting on you today.*. The faces beside it are a subset
  and say so in words under it (**Start with these 5 people**, 先看这 5 个人;
  a phone keeps the words of the count and leaves the faces to speak). The side
  has no large numbers to stare at: what can be approved at once is a worded
  button, **Approve all N** (一键批准这 N 件), counting only items that can go
  now (a reply waiting for you to fill a gap is not among them) and opening the
  approval sheet, whose title says the same N; what others owe is a worded link to its list, **See the N
  waiting on others →** (看 N 件在等谁 →); with nothing on others the link
  reads **Everything open**. With nothing that can go at once there is no
  button at all, never a greyed one or a zero. Today no longer asks **What
  should you remember about X?**: it picked a page REM already knew well, gave
  no reason and took no answer, so the card was removed rather than dressed up. A failed or stopped scheduled round shows one line above the
  date in the reader's language (*One round last night ran too long and was
  stopped; the next round continues.*), never the runner's own English, which
  stays on the line's tooltip. The cards lead with the first
  person whose reply REM has ready, so its Send is on the first screen; a line
  above the card says so (**Reply to Jiexuan Deng first: the reply is ready**),
  the headline still names the most urgent person, and that person's lane is
  the bold one. The open card is compact: the context is one line with
  **More**, the letter scrolls in a short window, and **Why this reply** sits under
  the reading in your language. It opens its draft in place with
  To, CC (**No one** when nobody is copied) and Subject; REM's
  `【需要你：…】` slot is a row to answer in, directly above Send and outside the
  letter's scroll window (the letter keeps a marker that shows your answer):
  buttons when REM wrote the alternatives (`邮件附件 / 共享文件夹`, `A 还是 B`), a
  text field otherwise; the date after the dash is never split into options.
  Until every question is answered Send stays disabled, and the line beside it
  names what is left (*1 choice left: Format*, the letter's own label for the
  slot or REM's words, short); a tap on the name goes to that question. The lanes show the five most urgent people on a desktop and
  three on a phone (always the open card's), then **N more people**; on a phone
  the context line and channel switch wait behind **More**, and Send comes into view with the draft, right
  under the question (with a long ask above the draft that is below the first screen). **Send** is the page's only
  green control. It sits under the letter and REM's question in normal flow, on a
  desktop inside the first screen; on a phone too, so it comes into view with
  the draft and never covers the message above it or the draft itself (it was
  pinned above the tab bar until 1.9.6, and on real data sat over the draft's
  first lines). When the Host lists an approval for the draft, Send holds the
  reply for 10 minutes: the person's card and lane close, the count steps down,
  and the line **Sent to …** keeps one **Undo** until the hold ends, when the
  Undo goes; without an approval the reply goes at once and the line says it
  cannot be undone. A snapshot shows Send disabled and one plain line for the
  page, *This is a snapshot: sending and handing work to an agent happen in the
  live reader*. Today, **Waiting on you** and **Reader settings** never show a
  command to copy (D-60).
  **What REM did overnight** adds **Replied to N people for you** when REM sent
  replies itself (`sent_by_rem`), and no row when it did not. Its lines count
  items (**3 things have a reply drafted**, with the people named), so they add
  up to the side line's **REM handled N things overnight**, and the
  **Overnight** section opens with the same number in one sentence before it
  speaks of pages; a page pass older than a day and a half is dated
  (*Pages were last updated …*) instead of being called last night.
  **A promise gone stale stops burning**: one whose date passed more than 60
  days ago, with no message on its thread for 60 days either (the span after
  which an undated thread goes quiet), is not counted among the people waiting
  and has no red. It is triage of the past, so it is not in the side column: one folded grey line under the
  desk, **N have gone quiet for a long time · Look** (N 件很久没动静 · 看看), opens in place, each row with the strip every Today row carries (**Mark done** · **Not now** · **Ignore**,
  then the hand-offs) and, beside the name, **Still open**, which brings it back to the count, and **Mark all N done**
  (都标为完成（N）, N counting the ones the fold does not show too) closes every one of them, each as its own mark
  (never linked as one thread), with one notice and one **Undo** that reopens only the marks the notebook kept;
  any it refused get one *Not saved · Try again* for just those;
  past three, its link *N more in Gone quiet →* opens Waiting on you with the folded **Gone quiet** section open and in view.
  Today's own **Gone quiet** fold leaves these promises out, so an item is one row on the page; Waiting's section
  lists them. A fold draws its rows when it is first opened. The Projects headline names
  only a live late promise in red and mentions stale ones in grey; both read the thread's last cited message.
  A promise with no dated message stays live. **Still open** is kept on this
  device with its day and holds for another 60 days, then Today asks again. Stale promises are counted with the
  quiet threads everywhere else too: not in the Waiting count, not red on **Waiting on you** or the People list.
  **The night chart gives its row back** when the last three nights hold fewer
  than two runs of reading or rewriting: it becomes one grey line under its
  title (*Last 3 days: no mail read and no page rewritten; REM handled 6 things
  in Today*, the same count as the side line) and the people waiting take the row.
- **Hand to Codex / Hand to Claude** (交给 Codex / 交给 Claude, D-100) sit as two
  quiet text buttons on every unfinished row: Today's cards, its long-quiet and **Gone quiet** folds, all three
  bands of **Waiting on you** (yours, on others, other open context) and its **Gone quiet** section, whether or
  not the night prepared it. A click posts `{"action": "run", "key": <the item's key>, "agent": "codex" | "claude"}`
  to `/rem/task`; a row the night did not prepare gets its task reserved on the
  spot from the row itself (its page, its text, its source), with the same
  receipt, prompt shape, Stop, Take back and status as a prepared one. The row then
  says where the work is, in place (on a Today card the row instead leaves the
  deck at the click and shows under **work in hand**, see **Today's order**
  above), and follows it by itself: **Codex is
  working · Stop · Take back from Codex**, then **Codex finished · See result ·
  Take back from Codex**; **See result** opens what the agent wrote (its
  deliverable, else its last message, `{"action": "result", "id"}`) under the
  row, and **Take back from Codex** (从 Codex 撤回交办) removes the work and
  brings the two buttons back; it never reads **Undo**, which undoes the item.
  The strip carries the row's three ways to close it, as words on screen, never an icon, before and after a
  hand-off, in one order everywhere (Today, its folds, Waiting on you): **Mark done** · **Not now** · **Ignore** ·
  **Hand to Codex** · **Hand to Claude** · **Show more** (**More** until sprint 22). In a saved snapshot (no Host, or a `file://` page) the
  closes and hand-offs are still shown but disabled, since nothing would carry a snapshot's mark to the notebook:
  each button says why when pointed at, and each card, band and fold says once, in words, *This is an offline
  snapshot; open REM to mark it.* (这是离线快照，打开 REM 后才能标记), with **Open the live reader** when this
  computer has one; E does nothing there either, nor do Still open, Not done yet, a record page's Mark done and Undo, or a draft's Skip, all drawn in the second ink with the same reason. A snapshot never writes a mark to the device. **Mark done** (标为完成: handled, settled offline included; `/rem/thread` state `done`), **Not now**
  (暂不处理: state `skipped`; since sprint 22 it asks when the row should come back and the notice says *Put off ·
  back on …*, see **Not now asks when** above; a mark without a date still returns only when new mail arrives on its
  thread and reads *Not now · returns with new mail*) and **Ignore** (忽略, for an ad or a notification: state `ignored`, which
  closes like `done` and never returns, but reads *Ignored* (已忽略) in its notice (*Ignored · this one will not come
  back*), its history line and the closed list's summary, which names the states it holds, e.g. *Marked done ·
  Ignored (3)*). On Today all three leave the same way, the row (or a one-row card) sliding out unless motion is
  reduced. When every mail the row cites came from one sender that looks like a machine or bulk mail (a
  no-reply or sending-subdomain address, or a notice sender the map set apart), and REM knows the owner's own addresses,
  Ignore's notice also offers **Stop showing mail from** *address* (以后不再显示 *address* 的邮件); one tap saves the sender
  (`POST /rem/sender {"address", "ignored": true}`, the same loopback, cookie and JSON rules as `/rem/thread`), the
  notice then says *Ignored · mail from* address *no longer shows here*, and its one **Undo** reopens the item and
  lets the sender back; a save the Host refuses says *Not saved · Try again* and changes nothing. REM never stops a
  sender by itself, never offers a person-looking address, and relay addresses that carry many different people are
  never offered. Shared notification mailboxes (`messages-noreply@…`, `notifications@…`
  and `calendar-notification@…`) are never offered either, including on custom domains.
  With labelled passages hidden, the address of a labelled row (and every address in Settings) shows
  only its domain. The list is `.state/ignored-senders.txt`, one `YYYY-MM-DD address` per line, and
  can be edited by hand (a bare address or `Name <address>` is read too): Today leaves out an item only when every
  mail it cites came from listed senders, the night drafts
  them no reply (an open draft to one says *This sender is ignored*), and **Settings → Ignored senders** lists each with **Show again** (恢复显示). Each notice keeps
  **Undo**. Mark done
  and the row's other actions on **Waiting on you** no longer repeat it, in
  green or quietly, whatever the row's reply state. On **Today** it is the
  same button: the row has no tick of its own, the strip's **Mark done** closes
  that row and it leaves the way every closed card does, with **Undo** in the
  notice. A card of several rows keeps the tick in its head, which closes all
  of them (**E**); a card of one row has none, and **E** still closes it. The
  card's green **Mark done** (shown when REM judges a row handled) is drawn
  only when it closes several handled rows at once (and when it closes every
  row, the head's tick is left out, since it would close the same); for one row it would repeat
  that row's strip button, so the card shows no green button and the row's
  strip, with its **Mark done** and REM's reason, is shown without a hover, on
  a phone too. Since 1.9.6 every row of the open card shows its strip line (and so Mark done, Not now and Ignore)
  without a hover or a tap, on a desktop and a phone alike; the notes under it (also on, the draft's reason,
  a task's result) still open on hover or tap. Since sprint 14 each card has one primary, chosen by what the
  item is: a ready reply's **Send**, else the card's green step (**Draft now**, **Approve**, a mark of several
  handled rows), else one row's control in bold: **Hand to Codex** for a debt the night prepared as a task, or
  **Mark done**. **Open** *name* is no longer a step (the name already opens the page). On Today the row strip is
  *Mark done · Not now · Ignore · Hand to Codex · Hand to Claude · Show more*, the lead among them in bold: the closes
  and the two hand-offs stay visible words (D-100), and **Talk it over** sits in the item's second level, behind
  **Show more** (更多背景; it folded under a worded **More** from sprint 14 to sprint 22). On a phone the three closes are the first line and the hand-offs and More the second. The card
  head's **S** button is **Next card** (下一张), shown with its word beside the glyph (the multi-row tick reads
  **Mark all done**): it only deals the next card and records nothing. A snapshot keeps Mark
  done in the row's own actions and the tick on Today, since its strip cannot
  act. A refused request is said in words on the row,
  never in the Host's own English: an item no longer open (400) asks you to
  reload, a changed item (409) too, an expired session (401) to reload the page,
  and no answer to try again shortly. In a snapshot the buttons are disabled and
  the page's one snapshot line says why, with a link to the live reader on this
  computer when it has one. Nothing in the reader says a task is recorded but not run.
- **Talk it over ▾** (聊一聊 ▾) ends the same line, *Hand to Codex · Hand to Claude ·
  Talk it over ▾* (since sprint 22 its two choices are in the **Show more** panel of the row, on Today and in
  Waiting on you alike), and opens the agent choice (**With Codex**, **With Claude**;
  和 Codex 聊这件事). A choice opens a conversation under the row: REM gives the
  agent the item (page, text, project folder, a work folder of its own), its
  first answer shows in the page, and the box under it sends the next message as
  one more turn of the same agent session (`POST /rem/talk`, actions `begin`,
  `say`, `read`; the page polls while the agent answers). Each turn runs through
  co ai's harness like a task, with the same access and the same "never push,
  merge, send or post" line. Replies, and **See result**, render as the
  notebook's own Markdown (paragraphs, lists, inline code, fenced code as a code
  block, links), escaped first so no HTML from the model runs; the transcript is kept at `.state/talks/ID/talk.json`.
  Opening it again returns the same conversation. When the live reader loads a
  newer page, the open conversation returns under its row with its context,
  replies and any unsent message; its composer continues the same agent session.
- **The reader's pictures are two published sets, never drawn by hand**: interface icons are Lucide
  0.468.0 (ISC) and service marks are Simple Icons 16.34.0 (CC0), copied from the published files;
  `connectonion/_licenses/rem-reader-icons.txt` names every key, its source and both notices.
- **The rail** (D-132, #3091) is a 72px column of places, each a picture with
  its word under it, in ONE order that reads from what you act on, to who and
  what it is about, to what the notebook concluded, to the raw material it was
  built from. A short hairline parts the four groups:
  **Today**, **Waiting on you** (*Waiting*), **Agenda** | **People**,
  **Organisations** (*Orgs*), **Projects** | **Knowledge**, **Decisions**,
  **Principles**, **Skills** | **Agent sessions** (*Sessions*),
  **Opportunities** (*Opps*), **Works**, **Memory changes** (*Changes*). At
  the foot are **Settings** and your face.
  **The rail shows as many places as its height holds, in that order, and only
  what does not fit goes under More**: at 1440×900 twelve cells fit (eleven
  places and More, or all twelve places of a notebook with no Opportunities or
  Works yet), at 720 the first eight and More, and from about 1000 px every
  place is in the rail and **More is not there at all**. The rail never scrolls
  and never clips a cell; it refits when the window changes height. **More**
  opens beside its button and lists the folded places in the same order.
  **Which places show**: the first eight every notebook has (Today to
  Projects, Knowledge, Skills) and Memory changes always show, and their pages
  have an empty state; Decisions, Principles, Agent sessions, Opportunities and
  Works show once they hold a page (or while you are on one), as they did
  under More.
  A short word is the start of the place's accessible name (*Orgs* is named
  "Orgs · Organisations"), so saying the word you see finds it. Tab moves
  through the places in the order you see them, then More, Settings and you;
  the current place is in ink, in bold, on a raised cell and is announced as
  the current page (`aria-current`), also when it sits under More. Your face
  opens your own page and shows **You · name** beside it on hover and on
  keyboard focus. Only **Waiting on you** carries a number; a category's size
  is not something to do. On a phone the rail gives way to the tab bar (Today,
  Waiting, People, Search, More); **More** opens a sheet with every place by
  its full name in the rail's order, the same hairlines between the groups,
  and Settings and you at its foot. There is
  no **Questions & connections** entry any more, as with Activity;
  `#reviews=1` still opens it, and **Memory changes** carries its one quiet
  link, beside **REM activity**.
- **Knowledge** (#2996) is the notebook's wiki and its one place for how
  records link: there is no **All records** any more. It **opens on the graph**
  (#3085): the rail's Knowledge (`#c=knowledge`) draws the two-way map of every
  linked record that All records used to draw, and its switch reads **Graph**,
  selected, then **Entries**. `#view=graph` and the old `#c=all` address open
  the same graph. **Entries** (`#c=knowledge&view=entries`) lists one row per
  topic, the most linked first, each row showing the people, organisations and
  projects it ties together as links; an address that names the entries always
  opens the entries. The phone follows the same default. Every record the All
  records list held is still in its own category (a rail place or **More**) and
  in search; **Graph** is also in the ⌘K palette. A list with one or two entries
  also offers **Explore linked records →** when the graph has links. With
  nothing linked yet the graph has nothing to draw, so Knowledge shows the
  entries instead, with **Entries** selected.
- **The graph says what it shows** (#3085, #3095). Under the heading is one
  sentence counted from the map, and it is also the key: each kind stands in it
  beside its shape with its count in words (*◎ 5 knowledge entries link ● 110
  people, ◇ 32 projects and ■ 24 organisations, with ▲ 6 skills and decisions.
  The busiest is …, with 19 links.*); the busiest record's name focuses it.
  There are no instructions. The map ends at the window's foot, so the sentence,
  the map and the quiet line under it (*A bigger mark has more links*, sessions
  folded, records that link to nothing) are on one screen at 1440×900 with
  nothing to scroll to. **Names on the map**: every knowledge entry is named,
  on up to two lines, then the twelve most-linked other records (your own page
  left out); zooming in names more, in proportion to the area the zoom opens.
  A name is cut only between words, with an ellipsis, is the translated title
  when the page has a current translation in the interface's language, and is
  placed right of its mark, else left, below or above, wherever it touches no
  other name and no other mark; a record with no free place goes unnamed, and
  the layout keeps the strip beside each named mark clear. Pointing at any mark
  says its whole name and its link count. **The panel** beside the map is as
  tall as its list: with nothing chosen, the knowledge entries with their whole
  titles (wrapped, never cut) and what each ties together (*15 people · 10
  projects · 2 organisations*), then the five busiest pages under a rule.
  Pointing at a mark for a moment previews it there (its kind, name, first
  sentence, counts, links and a neutral **Open … page →** button) and rings it
  on the map without moving anything. **One click on a mark opens that
  record's page**, as does Enter on the map while a mark is focused; the
  browser's Back returns to the graph with that mark focused and the pan and
  zoom you left. A row in the panel, a search result or `&focus=` focuses a
  mark instead: the map closes in on it and what it links. No colour on the
  page is saturated. **On a phone** the map draws only the knowledge entries
  and the records they link directly, names the entries, and fills the screen
  down to the tab bar with nothing under it and nothing to scroll to; an
  entry answers a tap within 22 px of its centre (a 44 px target however small
  it is drawn), a tap opens the record's page, one finger scrolls the page and
  two move the map. The filters are not shown there. A focused record's card
  (name, **Open … page →**) sits under a shorter map, above the tab bar, and
  its lists scroll with the page. The heading and the **Graph / Entries**
  switch are the same size at the same place in both views.
- **A knowledge entry, a decision and a principle read as one entry** (#3097),
  set like a reference-book article with its notes at the end. The page is
  printed **once**: the title, the page's own first paragraph as its lead, then
  its sections in the order the file has them. There is no summary block above
  and no **Full memory and sources** drawer below (those stay on people,
  organisations, projects and skills). The text is set at the body size with a
  line-height of 1.7 (the visual system's `--lh-read`) and a measure of about 34 Chinese or 70 Latin characters;
  a heading has clearly more room above it than below it; a line that is
  wholly the owner's quoted words is a quiet ruled block. A date written as
  `2026-08-27` in a sentence reads *Aug 27* (*8月27日* in a Chinese sentence);
  quoted words, paths and links keep their characters.
  **Sources come once and last.** Citations stay in the text as raised numbers.
  Every `Sources` block in the file, at any heading level, is gathered into one
  list after the last section. A file with a single `Sources` block keeps the
  numbers it was written with; a file with several (an older page that carries
  `### Sources` under each appended section) is renumbered continuously in
  reading order, and a source cited by two sections is listed once. Each mark
  links to its entry and each entry links back to every place that cites it.
  An entry says what the source is in words (*Coding session, 27 Aug*, *Mail
  from Mara, 3 Sep*); the raw identifier and file path are in the entry's
  tooltip and behind **Show identifiers**. Nothing follows Sources except the
  page's footer. **Drawn from** (the notebook pages an entry rests on) appears
  once per section, as links in an inset block labelled *Drawn from your
  notebook*, apart from Sources: one is where the learning came from in the
  notebook, the other is the evidence. *Also known as* is left out when it only
  repeats the title. The counters under a knowledge title (people,
  organisations and projects that link to the entry, sessions that name it) show
  only the ones above zero, and the row is absent when all are zero. The side
  column keeps the local graph and related entries; **On this page** appears
  from four sections up; on a phone the column folds below the text.
- **Headings name a page, they do not explain it** (#2994): a category page
  shows its name and its count, not a sentence about its order. Skills opens
  with its name, its view switch and its finder (*Find among N skills…*) on one
  line, then the family tabs with no caption, then the table. Today's number stands beside the faces it starts with, without
  *Start with these N people*. The graph's heading is **Knowledge** and its
  switch; its counts are in the one sentence under the heading, each beside
  its shape, and the panel lists the entries, then the busiest pages, divided
  by a rule. Sessions keeps its count
  without an explanatory subtitle; Projects keeps its factual summary at body
  size and drops the sentences describing its sort order and board axes. The
  [category heading audit](rem-heading-audit.md) records each keep/drop decision
  and inventories the former All records paths.
- **Your day** (今天的安排) sits on Today below the cards and the to-dos (it
  opened the page until sprint 22; see **Today's order** above) (#3058).
  The night saves `.state/day-plan.json` immediately after `.state/calendar.json`
  in the same background function, for today and tomorrow in `schedule.timezone`.
  This is deterministic: it uses saved events and Today's existing ranked items,
  with no model call, address lookup or calendar writes. To-dos stay in Today;
  no person, organisation or project page gains tasks.
  Events and proposals share one time-ordered list. Events include their calendar
  link, linked attendee pages and the location exactly as the calendar supplied it.
  A location without a number, a street word (street/st, road/rd, avenue/ave,
  lane/ln, drive/dr, boulevard/blvd, way, highway/hwy, terrace, crescent, court,
  place, square, 路/街/巷/道/号), or more than six words also says
  **address not in the calendar event** (日历事件中没有地址). This is a simple
  warning rule, not address verification; no location is expanded or guessed.
  At most five open, active items waiting on you retain Today's ranking. Each
  links to its source page and explains its deadline, promise or waiting date.
  Each proposal takes 30 minutes, on half-hour boundaries, using the longest
  remaining free gap first (earlier gap wins a tie). Working hours default to
  09:00–18:00; an optional `schedule.working_hours: {start: '09:00', end: '18:00'}`
  in `config.yaml` overrides them. There is no new settings screen. Overlapping
  events merge for availability. Only timed events take working hours: an
  all-day entry is listed at the top of its day as context and blocks nothing
  (one week-long all-day entry used to leave every proposal with no free time).
  A timed event shorter than 24 hours blocks the hours it covers on each day,
  and one that runs past midnight ends at 24:00 on the day it began. A timed
  event of 24 hours or more is a trip or a booking, not a meeting: it is shown
  as **All day** with the all-day entries on every day it covers and blocks
  nothing either.
  An event without a title says what it is. Google's focus time and out of
  office are **Focus time** (专注时间) and **Out of office** (不在办公室); an
  entry from a calendar shared as free/busy, or a private one on a calendar you
  can only read, is **Busy (calendar name)** (忙碌（日历名）), since Google
  sends no title for those; only an event of your own with no title is
  **No title** (无标题). Google's working-location entries are not saved: where
  you work that day is not an event. A meeting that is on your calendar and on
  a colleague's shared one is saved once, with its title. These labels are
  saved by the calendar read, so events saved before this change keep
  **No title** until the next night's read (or `co rem catchup`).
  A proposal row is its time (or **no free time today**) and **Proposed**
  (建议), then its sentence as plain text on at most two lines (the whole
  sentence is its tooltip), then why it is there and one short link: the name
  of its person or project page.
  Items that cannot fit say **no free time today** (今天没有空闲时间).
  Tomorrow's first event and every location tomorrow appear below the list.
  If no calendar has ever been read, one sentence says so and proposals have
  no suggested times. Saved plans show their date; a stale plan is labelled.
  The reader uses the saved plan offline. Since there is no `co rem today`
  command, `co rem status` prints the same plan as one text line, including
  tomorrow. `co rem catchup` reports the saved plan for each night.
  Failed calendar reads keep their last-read date and reason beside the plan.
  Before the first plan save, proposals are untimed; if a calendar was already
  read, the reader says the day plan has not been saved yet. Marking a proposal
  done hides it immediately; undo restores it without
  moving other proposed times. A question from you is not labelled a promise.
  Dated promises silent and overdue for over 60 days are set aside as Today
  does; the remaining proposals keep their existing order.
- **To-dos** (待办) sit on Today in their own short section above **Your day**,
  apart from events (#3087). The same background step that saves
  `.state/calendar.json` reads your open Microsoft To Do tasks (every list of
  `/me/todo/lists`, tasks whose status is not `completed`; the Microsoft login
  from `co auth microsoft` already carries `Tasks.ReadWrite`) into
  `.state/todos.json` beside it. Each row says in words that it is a **To-do**,
  the list it is on, and its due date: *due 20 Nov*, *overdue since 12 Nov*, or
  *no due date*; overdue ones come first, then by due date, and past eight the
  section says how many more there are. Nothing here is a button: a to-do is
  ticked off in Microsoft To Do, and the next read drops it. A read that fails
  keeps the tasks saved before and the section says when it failed and why,
  like a calendar; no failure stops the night. With nothing to list the
  section says one thing (#3085): **No open to-dos.** only when every connected
  list was read and none holds one; when a list was not read it names that list
  and why, and of the one that was read says only *Microsoft To Do has no open
  to-dos.* **Google Tasks are not read
  yet.** The Google login has only the calendar scope, so the section says
  *Google Tasks are not read: Google must be reconnected with access to tasks*;
  REM never adds a scope or starts a login by itself. Only the owner's own
  reader carries to-dos; a shared page has none.
- **Agenda** is a calendar (#2998), drawn as one: no heading, then **‹ Today ›**,
  the range in words, **Week / Month**, and under them one small line saying
  which calendars were read. **Week** is a time grid starting today (‹ › move
  it a week): hours down a quiet axis at 44 px an hour, hairline hour lines and
  lighter half-hour lines, seven day columns with weekday and date heads. Today's
  date is the one inked numeral and its head says **Today**; weekends are a shade
  quieter. Each timed event is a block placed by its start and as tall as its
  minutes (a 90-minute event is one and a half hour-rows), its title first, then
  its hours, then its place when the block is tall enough; a short event keeps
  the height of its title. Events that overlap share the column side by side;
  back-to-back events do not. A line across today marks now, and the axis says
  **Now 12:00**. The grid ends at the window's foot and scrolls inside it under
  the heads; it opens at 07:00, so 07:00–21:00 is on screen at 1440×900, earlier
  when the week's first event or now is earlier. Above the hours is the
  **all-day strip**: an all-day event is a bar, and one that runs several days is
  **one bar across its days**, never a card a day. A timed event that lasts a
  day or more (an afternoon to a morning two days on) is a bar there too, as a
  calendar draws it, saying its start and end times in words; it is never a
  block from midnight in the hours. A shorter one past midnight (22:00 to 01:00)
  stays a block on each of its two days. The notebook's own dates sit
  in the strip too, as outlined bars linking to their pages: promises with a due
  date (**Due**) and agenda pages on the date they state (**Noted**); one that
  is past due sits on **today** in red saying *Late, due Sep 25*, so there is no
  second list of earlier open items under the calendar (that line of links
  is gone: the same items are on today, and undated-late pages are in search and
  on their own dates). An empty day is empty: no placeholder. **Month** is a
  Monday-first grid of weeks (the reader's one week-start rule): each cell has
  its date, today marked and said, days outside the month dimmed; all-day and
  multi-day events are bars continuing across cells, then up to three lines in
  all of *time title*; what does not fit is counted in words (**+2 more**), and
  that count opens the day as a week starting there. **An event opens its
  detail** on a click: a small card beside it (a sheet from the foot on a
  phone) with its title, its time in words (*Fri 2 Oct, 09:30 – 10:00*; *All
  day, Mon 5 Oct – Wed 7 Oct*), place, guests (their people pages when a page's
  Email or Handles line matches, else a count), which calendar it is in
  (*In Google Calendar*) and **Open in Google Calendar ↗**. Which provider an
  event is from is also in its hover title; the edge of a block (ink for
  Google, grey for Outlook) is only a second cue. A timed event that crosses
  midnight is a block on each day it covers: its start time on the first,
  **All day** between, **Until 17:00** (到 17:00) on the last; one that ends at
  midnight is not on the next day. **Keys**: ← → move the chosen day, ↑ ↓ move
  it a week (the view follows), **T** is today, **Enter** opens the chosen
  day's first event, Esc closes the detail. **On a phone** the week is a strip
  of seven dates (tap one to jump to its day; a date with nothing is quiet)
  over a day-by-day list of three weeks, each day its all-day bars then its
  events in time order, a several-day event listed once with its range in
  words; the month keeps its grid with a count in each cell (*3*) and the
  tapped day's list under it. The layout is arithmetic in the page (`agBlock`,
  `agLanes`, `agBars`: minutes into pixels, lanes for overlaps, bars for
  spans), with no calendar library. The owner's own reader carries events and
  the plan; a page rendered for sharing (`render` without `local=True`)
  carries neither.
- **Agenda shows the weather for its days.** Each day that has a forecast
  carries a small line picture and *22° / 14°* in its column head (week) and
  its cell (month); the condition and the chance of rain are words on hover, in
  an event's detail and under the day's name on a phone (*Showers, 70% chance of
  rain, 20° / 12°*), where the strip of dates shows the high only. There are
  eight conditions (clear, partly cloudy, cloudy, fog, rain, showers, snow,
  storm); a day with no forecast shows nothing. The small line under the header
  says where it is for and from whom: *Weather for Sydney from Open-Meteo, read
  Today · 06:10.* **The reader never asks for it**: the night's calendar step
  (`weather.py`) reads the next seven days from
  [Open-Meteo](https://open-meteo.com), which needs no key and no account, and
  saves `.state/weather.json` (per date a condition word, high, low and chance
  of rain, with `saved_at`, `read_at`, the place and the source). **What leaves
  your computer, once a night**: the city's name to Open-Meteo's geocoding the
  first time (its answer is kept), then that city's coordinates rounded to two
  decimals to its forecast; never an address, a calendar entry or anything from
  the notebook. The city is `weather.place` (`co rem config set weather.place
  Sydney`); left empty it is the city of the notebook's timezone
  (`Australia/Sydney` → Sydney; a zone with no city, such as `UTC`, asks
  nobody); `co rem config set weather.place off` turns it off and nothing is
  fetched. Temperatures are °C, or °F where the place reads forecasts in
  Fahrenheit (the United States and a few others); there is no units setting.
  A read that fails never stops the night: the earlier forecast is kept and the
  line says when it failed, why, and when the forecast shown is from; a city
  Open-Meteo does not know is said as *not found*; anything that is not the
  provider's failure is a fault in REM, named with its exception and logged with
  its traceback in `co rem logs`. Only the owner's own reader carries the
  forecast. Open-Meteo's free API is for non-commercial use and its data is
  CC BY 4.0, which is why the page names it. Today's *Your day* does not show
  the weather yet.
  Events come from
  `.state/calendar.json`, which each background round writes once (scheduled
  sync, exec and native rounds, including `codex_exec`), outside the writer
  lock, from every account co can already read (Google after `co auth google`
  with a calendar scope; Outlook after `co auth microsoft` with `Calendars.*`,
  times asked in the notebook's zone): three weeks from yesterday in the
  notebook's zone, every page followed, cancelled events left out. **Only your
  own calendars are read** (#3087): in Google, a calendar ticked in Google
  Calendar whose access is `owner` or `writer`; in Outlook, a calendar you can
  write to (Graph's `canEdit`: true for one you created and for one shared with
  write access). A calendar shared as free/busy or read-only is never read, so
  another person's *Busy* entries are not in Agenda or Today, and events saved
  from such a calendar earlier are gone after the next read. `calendar.json`
  records, per account, how many calendars were read and how many were left
  out by access kind (`calendars`: `read`, and `left_out` counting
  `freeBusyReader`, `reader` and `unticked`), and Agenda says it in a small
  sentence under its header, above the calendar: *Google Calendar: 1 own calendar read; 3 left out
  (2 shared as free/busy, 1 shared read-only).* The reader never calls a calendar.
  No calendar failure stops the night: a calendar that fails keeps the events it
  saved before, and the page says when it failed, why, and when its events are
  from; anything that is not the provider's failure is a fault in REM, named
  with its exception in the page and in the round's result. Before any night
  the page says no calendar has been read; when none is connected, it says that.
  When a read found no events, Agenda says when the calendars were last read
  and that none were found. `co rem status` shows the last read and saved event
  count, or says that calendars have never been read or none is connected.
  `co rem catchup` includes the calendar result for each round, with the saved
  event count and any failed reads in its nightly progress line.
  Only the owner's own reader carries the events; a shared page has none.
- **Questions & connections** decides each pending review in place in the live
  reader: **Yes** / **No** / **Not sure** on a link, an answer box with **Save
  answer** / **Not sure** on a question. A click posts
  `{"id": <review id>, "verdict": "yes" | "no" | "answer", "response"?: <text>}` to
  `POST /rem/review` (owner cookie, like `/rem/task`), which calls
  `reviews.decide(..., author="owner")` and returns the updated review; the row
  then says **Recorded: Yes** in place, and the page rebuilds at once. A verdict
  `decide` does not accept, or a missing id, is a 400; a review already decided
  is a 409, said on the row as *Someone already decided this one*, and an id the
  notebook no longer holds is a 404 (*This one is no longer here*). A decided
  review names you as **You** (你), not by the stored author `owner`. **Not sure**
  posts nothing, so the review stays pending and **Change my mind** brings the
  choice back. These are quiet buttons, not green. A snapshot shows no buttons
  and no command, only *This is a snapshot; decide these on the live page*.
- **Waiting on you on a phone** puts each row's date under its title, so the
  text uses the full width.
- **Knowledge with no entries yet** says *REM files knowledge from your records
  on its night run* (the round's `backfill_topics`), with no command to copy
  (#2910).
- **Names on screen** come from the page's own heading (a line starting `# `;
  `##` section lines and `#Title` without the space are not headings); a heading that names a
  kind rather than one thing ("The draft", "Notes") gives way to an alias that
  does, then to the file's name. A topic nothing names but such a phrase stays
  openable by its path but is left off the lists and out of the graph, and the
  night run no longer files one. An organisation titled by its domain shows the
  name its page spells, either in full ("Stone Field" for `stonefield.example`)
  or as the name the domain shortens ("University of Brightlane" for
  `unibright.example`, only with *of*, *for*, *de* or *the* between words, each
  giving two letters or more, never a person's name, and only when it is the
  one such name that fits), else its people's **Company** link; it is marked
  *not yet clear what this is* only when nothing in the notebook names it.
  Graph labels are cut by width and only between words (any glyph of a Chinese
  title is a boundary), so a Chinese title stays inside its card.
  The graph's list of the busiest pages leaves your own page out: you are every
  page's hub by definition (the notebook's owner field, not a name).
- **Merged threads**: the same request copied onto several pages is shown
  once, with **Also on** naming the other pages. Copies merge when they cite
  the same message and one mostly repeats the other's distinctive words, or
  when dated within a week with matching wording. Written dates such as "23
  October 2026" or "Sep 3" count as dates. A page's undirected line can join
  a directed copy of the same request; two different requests in one email
  stay separate.
- **People** opens straight on its table (#2991): the page's name with a
  filter and **Columns** beside it, then one row per person with name,
  organisation, last contact, messages in the last 90 days, who wrote last,
  open items and page depth. There is no count of who is waiting and no link
  to Today: People is the record, and what you owe lives in Today. Rows start
  with the most recent last contact; people with the same date go in order of
  their latest two-way exchange (the older of your last message to them and
  theirs to you). Any column header sorts both ways, with blanks last either
  way and names in pinyin order in Chinese. **Open items** counts what Today
  would show for that person: not done, not quiet, not stale, not already
  answered. **Who wrote last** reads the last indexed mail between you; a group
  mail you sent to several people counts as *You* for each of them. Typing in
  the filter narrows the rows by name, organisation or role, and Enter opens
  the first match. **Columns** adds role, email, phone, the 52-week contact
  chart, warming or cooling, who writes first, reply times and mail count,
  remembered in this browser. One grey line under the table counts who is not
  in it (people you write to with no page yet, possible contacts held for
  review, service senders), and other contacts found in mail stay folded below.
  On a phone each row is a card and a **Sort by** menu replaces the headers.
- **Organisations** opens as a full-width tree table, expanded by default,
  with the most recently contacted organisations first.
  The default columns show a local logo or monogram, name, kind, what they do
  or mean to you, website, location, people known there, activity (messages in
  90 days), and last contact. Search and kind filters follow the reader’s
  language; activity stays a readable message count at row height. An organisation
  with no messages in the window shows a quiet dash and sorts last, like unknown facts. Kind chips
  include **Unclassified** for pages with no recorded kind; the reader does not
  infer one. Summaries and locations occupy at most two lines on desktop, with
  the full text in the cell's title and on the organisation page. Location
  qualifiers stay with the address. Uninvestigated summary placeholders show a
  quiet dash, including cached translations. **Columns** remembers your choices
  separately from People and can add first contact, subordinate unit count,
  legal entity and parent.
  Blanks sort last in either direction. On a phone rows become cards.
  Websites open in a new tab; when Website is Unknown, a contact's business
  email domain can supply a link marked **Derived** (free mail is excluded).
  A `Logo:` fact can name a notebook-relative PNG, JPEG, GIF or WebP; the reader
  embeds it in both live data and the self-contained snapshot, without fetching
  images from the network. Missing logos use monograms.
  Units appear directly beneath their parent, indented with guide lines at every
  depth, with the same columns. Parent names include their direct unit count and
  distinct people across the whole organisation. Disclosures collapse branches;
  each organisation’s collapsed state is remembered in this browser. **By structure /
  Flat** switches the layout. Sorting a column or filtering by kind switches to
  flat rows, with a quiet ancestry path beneath each unit name. **By structure**
  clears the kind filter and restores the tree and saved collapses. Search temporarily
  opens matching branches. A unit whose parent is missing stays findable in the list.
  The book page names all contacts when there are at most four; otherwise it
  names the four most recent and says so. Its opening uses the earliest recorded
  first-contact date from the organisation or its contacts, including mapped mail
  and index dates when there is no written history. Business, location and website have
  separate labels, and the website is a link.
  An organisation page shows an indented, collapsible tree: organisation →
  units, courses or teams → people, with most recently active branches first.
  People keep their role in each unit;
  those without a known unit are folded under **Department not known yet**.
  Click beside a name to expand or collapse; the name opens its record. Tab
  enters the tree once, arrows move between rows, Right expands or enters a
  branch, Left collapses or returns to its parent, Home/End move to the first/last
  visible row, Space toggles and Enter opens the selected record.
  The breadcrumb comes first on a phone. The tree is the people directory;
  repeated contact lists and the local graph are omitted from this record.
  A person with several unit memberships appears once, with those roles together.
  The page reads as an article in one centred reading column: opening sentences
  give its summary, relationship, people known and first/latest contact dates.
  Mapped placeholders are omitted: the opening starts with what is known, a
  connection without a summary is just its linked name, and absent facts have no label.
  A known location or website is shown even when no description is recorded.
  The tree is followed by the organisation's own dated History as prose milestones,
  connections as text links, and facts and sources at the foot. Correspondents'
  activity is not the article's body; **Full memory and sources** keeps the page's
  complete record reachable. **View sources →** at the top opens citations;
  **Read full memory →** at the foot opens the complete record. There are no update badges, contact charts,
  freshness dots, branch bars or questions asking for action on this page.
  Organisation lists and pages carry no
  waiting groups, task chips or Today counts; to-dos live in Today.
- **Agent sessions** keeps topic tags and the outcome separate on each list
  card. A session page shows its summary, then the visible transcript, followed
  by decisions, follow-ups and artifacts. The transcript retains your turns
  and the complete final reply; missing intermediate activity is disclosed.
  Find searches the retained text, and source links land on the corresponding
  turn when it is archived. Other source rows open under **Details**.
  **Continue with Codex / Claude Code** goes on with the session itself, in the
  page: the agent resumes its own session id in the folder it ran in and its
  reply shows below, with a box for the next message (the same `/rem/talk`
  conversation as above). No resume command to copy (D-60); a snapshot says the
  live reader does this, with its link.
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
- **A person's page is their record** (owner, 2026-11-08): no list of what
  you owe and no **Mark done** there; one quiet link, **N items in Today**,
  when Today holds something of theirs. Right under the header comes
  **Open topics** (**还没结的话题**), what is still open with them, because it
  is what you open a person for: the top three, and **All N entries**
  (**全部 N 条**) opens the rest in place. On a phone the face stays in the
  header beside the name. Directly under the name is the **profile card**
  (owner, 2026-11-18: "the card should be the first thing shown"): every known
  fact as a label over its value, with nothing to expand, in four groups —
  **Contact** (email, phone, handles with their platform named — GitHub,
  Discord, LinkedIn —, links), **Work** (signing entity, project, a unit with no
  page of its own), **Relationship** (how you know them, first and last
  contact, mail) and **Identity** (also known as, language, location, time
  zone). Role, organisation (a link to its page) and units are the line under
  the name, and are not repeated in the card: each fact has one place. A
  click on an email, phone or handle copies it and says so. A phone is a
  handset; a handle on GitHub, X, WeChat, WhatsApp, Telegram or Discord carries
  that service's published mark in the page's ink, and one with no published
  mark (LinkedIn, Slack, Microsoft Teams) is an @, its platform named in words
  either way. Unknown facts are
  one quiet line, **N facts not found**, never rows of "not found"; citations
  are small numbers after the value; a labelled ([personal]/[sensitive])
  value hides with the labelled passages. The name is the page's one large mark;
  it carries its script as `lang` and hyphenates (where the browser has no
  hyphenation dictionary and a word would overflow, the reader adds soft
  hyphens at likely syllable joins; copying the name drops them). Under it
  the first role is shown as a title (its value and any qualifier that is
  part of it, "Events Coordinator (Entrepreneurship)"), then a neutral
  **+N**, never cut inside brackets; where a value came from ("email
  signature through …") is in the tooltip. Under that the **fuse** runs from the first exchange REM knows to today, one
  tick per dated History line at its real date; when the record has no dated
  lines it draws only the first contact and says so. The fuse turns red only
  from their last mail, and only once that is past your own median reply time
  in synced mail, and never while Today has her items handled, looking
  handled or needing no reply; without that data it is never red. Then mails,
  first exchange, your median reply and last contact (Open topics, above
  them, are the record's open threads as words and a date with nothing to
  click; marking them happens in Today); **In their words**,
  their own archived mail said to you personally: you on To or Cc (your
  addresses from the map and mail archive; unknown addresses quote nothing),
  at most eight recipients, not an auto-reply, cited by a public passage and
  by no [personal]/[sensitive] one, the excerpt itself unlabelled, greeting
  and signature block removed; the archive keeps no Auto-Submitted or List-Id
  header, so these are what it judges by. Each carries its channel and source
  mark; and
  the dated exchanges. Contact, organisation, what REM is not sure of (dashed,
  REM's pencil) and the local graph sit in the rail. On Today, a card REM
  thinks your reply already handled offers **Not done yet** (**还没办完**)
  beside **Mark done**; it is kept on this device, and the item stays in
  Today and on the People list. Project and organisation pages show each date once,
  under the title, in the reader's date format; when the file was last
  updated is noted in the Full memory and sources header. An organisation is
  private only when its title carries `[personal]`/`[sensitive]` or its Kind
  is personal. A labelled passage in its body shows with its label in the
  opening, facts, dated milestones and full memory, and hides alone when
  labelled passages are hidden, as on a person's page.
  A labelled membership (the org's own roster line, or a
  Company, Unit or Role in unit line on the person's page) places nobody in
  the organisation and draws no edge on the map. A project's folder path
  stays in its full memory, never as a fact on the page. A session summary
  that opens a sentence with "The owner asked…" or "Owner 询问…" reads as
  You / 你; "the owner of", "is the owner", present tense and a named owner
  are left as written. In 中文 mode,
  Facts values and Related pages snippets come from cached translations
  when they exist, and otherwise show the original with a 原文 mark.
  Investigated records omit the redundant status pill; mapped and partly
  investigated records keep it, and reviewed skills say **Source reviewed**.
  A person, organisation or project page with no translation yet carries no
  mark above its name (the old 原文 chip read as jargon). When its translation
  is on its way (opening it in the live reader queues it, or the reader's
  language is a nightly translation target) one quiet meta-size line under
  the header says **中文版还没好，先看原文**; its tooltip says whether it is
  queued for the next pass or background updates are off. A page simply in
  English with nothing requested says nothing. Opening the page only queues
  it, so the reader never says "translating"; cached translations preserve the original Sources lines.
- **Candidate correction for Related pages (#2624):** repeated snippets may be
  compacted only when their text, origin page, citation IDs, privacy state and
  original/translated state match. A destination page's introduction is never
  substituted under another page's source labels. Qualified or distinct evidence
  stays visible. This is pending review/publication, not behavior claimed for rc12.
- **Projects** opens on a board with **Active**, **Waiting**, **Quiet** and
  **Done** columns. Cards name the next step and who holds it; late promises
  stay visible on their card. Waiting means every confirmed open step is with
  someone else or an agent. Quiet follows the existing activity rule; Done
  requires an explicitly completed project. Longer columns unfold in place;
  on wide desktop screens an empty state keeps a narrow header and its zero count; on a phone
  the columns stack. **List** and **Timeline** remain available.
  The board's four-way switch stays in one horizontally scrolling row on a phone.
  A project page leads with the same state, up to three next steps (overdue
  owner-held steps first), and recent sessions or dated history. **+N more**
  opens the remaining steps in **Full memory and sources**. Purpose, findings,
  facts, people, decisions, detailed sessions, tags, local graph and history stay
  in that disclosure, which opens by itself (#3104). Source markers beside steps still open their evidence.
  Open steps share one frame and align each item's action buttons. **Agent request**
  (给智能体的请求), **Owner unconfirmed** (待确认负责人) and **Answer available**
  (已有回答) distinguish a request from an unassigned step and a retained answer;
  none of these labels claims a running task or an accepted hand-off.
- **Other record pages** open on a focused status, next exchanges, compact
  facts, related records and filterable dated Activity. Connected cards without a snippet stay compact;
  desktop cards with snippets align their source dates across each row.
  When only part of its queued or archived session history was read,
  the page says how many inputs were supplied. Explicit links and unambiguous name
  mentions make cross-page cards and backlinks; their labels distinguish a
  link from a mention. The original prose, every Facts/Contact field,
  Insight, History and Sources stay under the always-visible **Full memory and
  sources** disclosure, open by default and foldable (#3104). A claim
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
  marked. Cited conversations show the cited message, highlighted, with up to
  two archived messages before and after it. Each page shows only windows around
  its own citations, even when other pages cite the same conversation. Navigation
  closes an open source dialog. Mail headers stay visible while the body scrolls
  to a highlighted passage. Dates use one format in the notebook’s time zone.
  The owner remains accessible through **You**, outside the People list. Excerpts labelled `[personal]` or
  `[sensitive]` appear only in the reader on this computer (the snapshot and
  the local live reader), behind **Hide labelled passages**; the O Chat view
  never receives them and starts with labelled passages hidden. Missing original bodies are labeled, never
  replaced by a generated summary. A page only mapped from metadata shows its
  queue status and a count of sections awaiting investigation; written pages
  name their remaining gaps. Private projects retain an explicit investigation
  command. Empty Agent sessions shows queued status when background updates
  are enabled, or pending status when they are off, without import controls.
- **Full memory and sources opens by itself** (owner, 2026-11-18, #3104). On
  every record page the disclosure starts open and can still be folded. Its
  **Sources** (来源) leave the prose column for a full-width band under it,
  two rows a line on a wide screen and one on a phone. A row is one line:
  the source's number, what it is in words, then its kind, who and its date
  once. Mail shows its subject (and an attachment's file name), a coding
  session its title, a file its name, a web page its host and path, an
  investigation **REM investigation** (REM 调查); a mail missing from the
  snapshot says so in grey. The raw id is only in the row's tooltip. Rows are ordered by how many lines cite them, then newest;
  the first 10 show and **Show all N** (显示全部 N 项) opens the rest. Kind
  chips (**All · Mail · Sessions · Files · Other**, each with its count) filter
  them, and above 20 sources a filter box matches title, who and id. Each row
  says **Cited N×** (被引 N 处); pressing it jumps to the next line that cites
  it. A citation chip still opens the source panel, which now offers **Show in
  sources** (在来源中查看): it reveals and lights the cited row(s). The heading's
  anchor is always `sources`, in every language. On a Facts card an address
  wraps only after `@`, and empty fields fold into one quiet **N not found**
  (N 项未找到) line that names them. The standard section titles
  (Insight, Who they are, Why they are here, Our relationship, How they
  communicate, How you write to them, Cadence, Uncertainties and their
  siblings) read in 中文 in the zh reader, while their anchors keep the
  written English title (`&h=uncertainties` works in both). Quotes in the prose are no longer
  underlined, and a citation chip underlines only on hover.
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

Design ("Fuse"): the whole reader is painted from one token sheet at the top of
`reader.html`: one paper, one ink, one grey, one hairline; green only on the
primary action, which turns over on hover (green label on dark green); red only
for overdue and danger; and pencil, always dashed, for what REM inferred. Pencil
never colours text: an inferred word is grey with a dashed pencil underline.
Four type sizes: display (min(112px, 22vw)) is kept for the one thing a page is
about, Today's count or an entity's name, then 24, 16 and 12; two weights (400
and 700); square corners and no shadows. Rings that used to be shadows are
hairline outlines, and keyboard focus is a 2 px ink outline that wins over them,
except on `#main` and the Today cards, which are focused by script. Every CSS
transition and animation takes its duration, delay and easing from the sheet, so
`prefers-reduced-motion` zeroes all of them; the graph's zoom and the reader's
smooth scrolling are script-driven and check reduced motion themselves. The
graph tells kinds apart by shape (a session is a bar, a person a dot); a private
record is its outline with a slash. Dark mode redefines the same colour names
under `prefers-color-scheme` (unless the reader is set to Light) and under the
Dark setting. `tests/unit/test_rem_reader_style_sheet.py` scans the whole page
(styles, style and SVG attributes, url() data, the script's style writes and the
strings it builds) and fails when a font size, weight, radius, shadow, colour,
transition or animation timing is written outside the sheet, when a layout
custom property holds anything but a length or a number, and when a sheet token
is unused. A value that only exists at run time, such as a colour held in a
script variable, is outside what it can see. One system face carries Latin and
CJK and a mono face carries code; both are local, so the page makes no network
request. Every view fits a 390 px phone without sideways scrolling.

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

co rem gathers mail bodies and an attachment index (name, MIME type, size and
mail ID) before the model starts. Investigation selects documents bearing on
terms, money or identity and downloads them with `co gmail download` or
`co outlook download` into its task directory. Each PDF and DOCX is cited or
skipped with a reason in the run's lead ledger. Existing cached files are kept.
The investigation Skill also supports read-only research and records unavailable
sources in the lead ledger. Before 1.8.8 investigation ran Codex with
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

Codex compresses older sessions in place: `rollout-X.jsonl` becomes
`rollout-X.jsonl.zst`. On one machine about 22,000 of 22,800 Codex session
files were compressed, and REM read none of them: a first map saw only the
newest few weeks, and the next map would have cut skill counts to what the
plain files held (#2943). Every reader of coding sessions (sync, the shared
map pass, session pages, project filing and discovery, skill counts and
samples, the claim check of a cited line) now reads a `.zst` session as the
plain bytes it holds, streamed rather than unpacked to disk. Read progress is
the plain file's offset and hash and is kept under the plain name, so a session
read before Codex compressed it is not read again; a fully read compressed file
also keeps its own size and is not reopened until it changes. A session present
in both forms while Codex compresses it is read once, as the plain file.

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

Selected PDF, DOCX, XLSX, PPTX (including tables/notes), plain text, HTML and ICS
attachments can be read; XLSX needs `pip install 'connectonion[rem]'`, and
without it a spreadsheet is named as unread with that command. Investigation passes full extracted text to chronological
digest chunks instead of dropping a long attachment's tail. Unreadable
formats/errors remain visible. Attachment text is saved as a research capture
and cited as `gmail:<short mail id>:<filename>` or
`outlook:<short mail id>:<filename>`; the metadata index is a reading guide,
not evidence. Billing notices from an organisation's domain enter its material
when their subjects concern invoices, receipts, ABNs, billing or payment.
Legal identifiers belong only on the page of the entity they name, including
the owner's own company. The Skill supplements from the account's
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
the outer process 30 seconds to exit afterward. The common native adapter
therefore closes its delegate before co rem process timeout is reached.
At its deadline the Codex adapter sends `turn/interrupt` for the running turn
(waiting at most 5 seconds for the answer), archives the thread, and kills the
app-server's process group at once; only then does it answer `timeout`, so the
task is parked after its worker has stopped. Until 2026-11-17 it sent no
interrupt and closed the server with a grace period, and one timed-out
worker's thread went on editing its task folder for about 7.5 minutes into the
next task's time. Claude Code's process tree is terminated at its deadline as
before. If `co ai` itself has to be killed at the outer deadline, its
app-server is not reached (it runs in a session of its own): that case is not
handled yet.
Either timeout is the same failure of that one turn (`co ai timed out after
Ns`), with the tokens the adapter reported: `co rem exec` and catchup park the
task and take the next one, and a stage run retries the call once.

## Scheduling and accounting

Codex notebooks on macOS use `schedule.runner: codex-exec` by default when the
Codex CLI is installed and signed in. launchd runs `codex exec` directly through
REM's turn worker, using the same work-loop prompt as the desktop automation.
Exec sessions can continue across tasks; desktop automation sessions can end early.
The model remains `model` (default `gpt-6-luna`); `effort` defaults to `medium`.

`effort` is the reasoning effort of every Codex worker REM starts, not only of
the scheduled turn. The turns that `co rem exec`, `co rem catchup`, sync,
investigate and deepen start are `co ai --harness codex --effort <effort>`;
the scheduled `codex exec` turn and the cited-claim audit get
`-c model_reasoning_effort=<effort>`; owed tasks and conversations pass it to
the same adapter. Until 2026-11-17 the `co ai` turns and the audit passed
none, so they ran at the owner's own `~/.codex/config.toml` setting: 81 worker
turns of one night at `max` while `config.yaml` said `medium`. Claude Code and
COAI runners take no effort from REM, and their records say none.
`speed: fast` (the default) asks Codex for its priority service tier on every
turn; `standard` leaves the tier Codex is configured with.

Every run record keeps what its worker was started at (`harness`, `model`,
`speed`, `effort`); a task `co rem exec` or catchup drives records its stage's
model and runner, where it used to name the notebook's. `co rem status` says
it under the last run:

```text
Last run         daily-update projects/fern.md · completed
                 2026-11-17 01:12 · 1 page changed · … tokens in · gpt-6-luna at medium effort, fast
```

```bash
co rem config set schedule.runner codex-exec effort high
co rem start
# To use Codex desktop Scheduled instead:
co rem config set schedule.runner codex-app
co rem start
```

Both modes fire at the saved starts plus the same 15-minute follow-ups.
The saved timezone must match this computer for these Codex modes. Exec runs
with the PATH captured at installation, including user command directories.
The resolved Codex executable is pinned in the job's `CODEX_CMD`; set this to
the CLI executable itself, then run `co rem start` to apply a change. Python,
shell and REM launcher commands are rejected to prevent recursive launches.
Each turn has a process lock: a fire during a running turn returns `busy` and
is skipped. A turn ends after at most three hours, terminating its whole process
group, including child tools; the next fire continues the round. Keep the computer
awake. No desktop app is needed for exec.

`co rem start` switches clocks: exec pauses and removes the desktop definition
and wake plist; app removes the exec plist and installs its automation and wake
job. Account-managed desktop tasks still require a confirmed pause before switching.
`co rem status` shows the installed runner and last exec turn result. Exec logs,
last messages and receipts are under `.state/turns/`; `.state/last-turn.json`
points to the latest turn. `co rem stop` removes the clock; a running turn can finish.
Environment loading, configuration and command resolution have a five-minute
deadline to bound hangs while allowing slow machines to start. Receipts record
this preparation time as `started_codex_after_s` before dispatching Codex;
`co rem status` displays it as `Codex startup`. This is a fixed upper bound;
a start still taking longer than five minutes fails even if it is progressing.
Configuration, command resolution and spawn errors leave a failed receipt with
the reason, which `co rem status` displays alongside the turn log and the command
to restart after fixing the cause.

`co rem next` has ten minutes to prepare a task. Every minute it prints what it
is waiting on, with the step inside the page: `Still preparing people/<page>.md:
gathering codex sessions (212 s on this step, 240 s so far)…`. The steps are the
investigation's own stage names (`gathering sources`, `listing <mailbox>
attachments`, `searching <mailbox> mail`, `gathering <mailbox> mail`, `gathering
<source> sessions`, `searching project documents`, `preparing evidence`,
`writing evidence files`). At the deadline it prints `Where the time went:` with
the seconds of each step, writes the same numbers to the turn log as a
`rem.preparation_stalled` event, and exits 75. (Inside `co rem exec` and
`co rem catchup` the process goes on to the next page instead; see catchup.) The page it was preparing is
parked with the reason in words (`parked: preparing it passed the 10-minute
deadline while gathering codex sessions`), listed under Parked in `co rem
status`, left out of the rest of the round, and retried by the same rule as a
page refused again and again: after 20 hours, at most three times on the same
material. The next `co rem next` serves other work. Pages the call had already
passed over before the one that hung are not prepared again.

A turn that exits 0 is `completed` only when a task was served, a submission was
accepted, or its last `co rem next` answered without a task (not due, round
done, a cap or the floor). When its last `co rem next` passed the deadline and
nothing was served or submitted, the receipt says `failed` with
`produced_nothing: true` and the reason in words. `co rem status` and Today
count these in the same sentence as failed turns: `Background: the last 3 turns
ran but produced nothing, since …`, or `the last 5 turns failed (2 ran but
produced nothing)`. An idle turn is completed and ends the count. A turn in
which no `co rem next` was recorded stays `completed` and says `No co rem next
was recorded in this turn`: the record's absence does not prove the turn was
empty.

The session window (what the owner typed in coding sessions, shared by every
page) is saved under `.state/session-windows/` and reads only rollouts that
changed. A rollout Codex has compressed to `.jsonl.zst` is read once more, by
itself; a deleted one takes only its own messages out of the window. The window
is saved every 512 MB walked, so a build ended by the deadline resumes.

`searching project documents` lists the notes (`.md`, `.txt`) of every folder
a project page names, and waits at most 5 seconds for one folder's listing.
macOS holds the listing of a folder under `~/Documents`, `~/Desktop` or
`~/Downloads` until someone answers its privacy prompt, and in the background
nobody does: two such folders held one page's preparation for the whole ten
minutes (2026-11-16), while the other 33 folders took 1.6 seconds together. A
folder not listed in time is left out of this search and named in the page's
coverage (`skipped 1 project folder(s) not listed within 5 seconds: <folder>`); the
search goes on with the others. While that listing is still held, later pages
skip the folder without waiting again.

REM treats an unreadable folder named in a coding session or scan as having no
Git repository; that folder does not stop round preparation. Other file access
errors name the affected path without blaming the notebook files.
If `co rem next` fails to prepare a task, the background turn is recorded as
`failed` with the error even when Codex exits zero. Its traceback is saved in
the turn's `.state/turns/*.jsonl` log. A successful retry clears that turn's
failure, while keeping the traceback; an idle turn remains `completed`.
`co rem status` and the reader's Today show the consecutive failed-turn count
and when the streak began (UTC). Status also shows the last error and points to
`co rem logs`. A completed turn ends the failure streak.

For `codex-app`, the desktop adopts a private local automation definition.
Its wake job opens Codex 15 minutes before each fire. Keep the app open and the
computer awake. Completed native wrapper conversations and REM's internal Codex
calls are archived, retaining trace IDs without filling active project history.

`co rem start` stages a paused task and verifies native index adoption before
removing an old launchd clock. A running old batch or failed registration leaves
the previous clock intact. Run start again after that batch finishes or Codex
initializes. `status` distinguishes registration, first execution, a stopped app,
an overdue trigger and a failed REM pass; a file alone is not a working schedule.
`stop` pauses the native task and retains its history. It does not cancel a native
model turn already in progress.

New `co rem start` registrations on a Mac with a ready Codex CLI use the
`codex-exec` OS job to run the native REM task loop through the existing Codex CLI.
Select `schedule.runner=codex-app` to keep the desktop scheduler.
Switching saves the desktop automation as PAUSED. If Codex's index has not caught
up within the wait, REM installs the exec job and records the switch anyway,
printing that Codex will pick up the saved pause. Before each exec turn REM reads
Codex's `automation_runs` index and skips the turn if this notebook's desktop
automation fired in the last ten minutes. Account-managed automations still need
to be paused through their supported management interface.

The native adapter in rc21 uses Codex's legacy local-file registration. Newer
desktop code also has account-managed registration, which can replace the local
file and task ID. That registration route has not passed REM's live acceptance;
the presence of a TOML parser or an enabled feature is not proof of compatibility.
The normal-profile follow-up on 2026-10-24 verified real native execution,
auto-archiving and pause after opening the existing app's Scheduled entry point.
A running App Server alone had not advanced its registered timer.
This verifies execution, not exact requested-minute timing: the cold retry
requested 20:35 Sydney, was indexed for 20:36:33 and began at 20:36:34.
Check `co rem status` before relying on unattended upkeep;
`co rem sync` remains available by hand.

**In opt-in preview 1.9.3rc22:** initialization opens the normal installed
desktop directly at Scheduled, including when its process is already running,
then independently confirms activation. After the native index is ready it
opens Scheduled again, so a cold launch does not depend on an early URL request.
It rechecks the same registration before removing the old clock; migration or
a concurrent change aborts that handover. Stopping a desktop-native registration waits for pause acknowledgement.
The codex-exec migration described above accepts a saved PAUSED definition. A known account-migrated task is identified
by its legacy association and requires management in Codex Scheduled until an
authoritative account registration API has been verified. REM does not recreate
its old file or treat a cached account status as confirmation of a pause.

Other model runners and desktop-mode notebooks with a different saved timezone retain
the legacy launchd sync job. Its five-minute tick keeps the saved timezone and coalesces missed slots.
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
- **Only a run with its own reading joins a group.** A round keeps one record
  for itself that lasts as long as the round, with no reading and no tokens.
  Those records used to join every investigation of a day into one group, which
  then cost the whole day's meter movement, your own coding included: a night
  read "38 of 35 points" and held 332 pages when investigation had used under
  one. A run without a reading now counts alone, from its tokens.
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
  Only investigation waits: the round's other stages run on
  ([what each budget holds](#commands)). A round's Abstract tasks do
  not count toward it.
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
- **A round the floor stops is a pause, and REM says so.** A notebook at the
  floor did nothing for two nights (71 scheduled turns, each ending with no
  task) while status, the night stats and the morning note all read as a
  quiet night. Now the first turn the floor stops records the pause in
  `.state/quota-paused.json` (when it began, the week's percent, the floor and
  the reset), and later turns keep that start time. `co rem status` leads with
  it:

  ```
  Codex week      Paused since Mon 09 Nov 17:00
                  This week's Codex allowance is 90% used, at the 90% floor kept for your own work.
                  No investigation runs until the week resets Wed 11 Nov 17:46; mail is still read.
                  → To let REM work before then, raise the floor: co rem config set limits.quota_floor_percent PERCENT
  ```

  The morning note's first line is `REM paused: this week's Codex allowance is
  90% used. It resumes Wed 17:46.` (Chinese: `REM 暂停中：本周 Codex 额度已用
  90%，周三 17:46 恢复。`), sent every morning the floor holds, with
  `"paused": "quota"` in that date's `morning.json` entry; a night the floor
  held at any time carries `"paused": "quota"` in `night-stats.jsonl`. The pause
  ends at the first turn the floor no longer stops, or when the week resets.
  `co rem status --json` always has a `paused` key: `null` when REM is not
  paused, otherwise `{"reason": "quota", "since", "used_percent", "floor",
  "resets_at"}` (`resets_at` in Unix seconds), so a script reads one field
  instead of testing whether it exists.
  Waiting and raising the floor are both the owner's choice; REM changes
  neither, and does not move the work to another runner.
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
the run before and unfinished pages from the existing queues, all of them in
the round. Both stop at the weekly budget or the floor and
record how many pages are left ([details](rem-people-pages.md#the-daily-round-four-runs-two-jobs-1723)). Initialization maps sources first, then runs a model investigation of the selected pages; manual
investigation remains outside the scheduled cap.

The UI is a static snapshot of the notebook as of its last render (the footer's **Updated** time); run `open` again to see later changes (`--no-launch` says so and ends on `co rem open`). No merge,
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
A page the count already holds is left out of People, and counted with the
service senders, when its title is a bare domain (`acmecloud.com`) or its every
address is a support, help, billing, ticket or no-reply desk (`support@`,
`help+4417@`), however often the desk replies; a person writing from their own
name at the same company stays (#3004).
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
  - **person**: Email, Phone, Company, Role, Team, Location, Time zone, Links,
    How we know them, First contact, Last contact, Signing entity, Handles,
    Language, Also known as
  - **project**: Repository, Stack, Status, People, Organisation, Started,
    Last activity
  - **organisation**: Kind, To you, What they do, Website, Location, Legal entity,
    Your contacts, First contact, Last contact
- An empty field is exactly `Unknown`.
- Organisation `Kind` is `university`, `investor`, `client_partner`, `supplier`,
  `community`, `own_company` or `personal`. `To you` is one sentence in the page
  language about the owner's relationship. Both require citations.
- A person's `Team` records a cited unit/team name only when evidence names it.
  A project's `Organisation` links its evidenced organisation as
  `[[orgs/fernhill]] [1]`; existing relative Markdown links work too.
- `co rem doctor` reports missing organisation pages linked from `Company`, with
  a correction/create instruction, and non-person pages filed under `people/`.
  Explicit entities and shared mailboxes are excluded from the people count,
  including investigated pages; doctor does not move or rewrite them.
- A field with several values separates them with `; `. Each value may end in
  a `(qualifier)` (`work`, `mobile`, `personal`) and then its citations
  `[n]`, which are numbers defined under `## Sources` like every other claim.
  A value may be a Markdown link.
- Dates (`First contact`, `Last contact`, `Started`, `Last activity`) are
  `YYYY-MM-DD`.
- On people pages, `First contact` and `Last contact` are the earliest and newest
  messages involving the person's own addresses that the person or the owner
  sent (a third party's group mail never counts, regardless of group size) in the
  retained archive, in the notebook's time zone. They are recomputed after
  promotion and on sync; they describe the archive's bounds, which may not span
  the whole relationship.
- On project pages, `Last activity` is the newest valid day listed in the page's
  own `## Sources`, with a citation to that source. Sessions, mail, chat,
  commits, documents and other dated sources use the same rule, including for
  projects without a repository. Code recomputes it after promotion and at the
  start of every night round, replacing `Unknown` and model-selected dates.
  An older dated "quiet since" status is cleared when newer evidence contradicts it.
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
named to call beside it. What goes is listed under `contacts_unverified`, and
the claim audit is told: its packet lists these values, and the owner's own
that were taken off, under `runner_removed`, with the rule that their absence
and an `Unknown` in their place are not findings. A finding that names one of
them anyway is kept in `claim-review.json` under `runner_removed_findings` and
does not refuse the page: the writer cannot put back what code removes. An
unknown `Company` can be filled from their own organisation email domain when
it maps unambiguously to an existing organisation page. Student subdomains
can name a university affiliation; `(from email domain)` does not establish
employment. Free-mail, relay, agent, and addresses marked shared or role never supply it.
An unknown `Time zone` takes a cited, unambiguous `Location`, or, when Location
is Unknown, a single-zone country email suffix (such as `.sg` or `.uk`).
These deterministic basics run in both native and in-process promotion and on
every sync, with numbered Sources citations. Populated Company and Time zone
values are preserved; contact dates always follow the archive.

People coverage in `co rem status` and the reader uses correspondents
across the retained archive who meet the page rule: mail both ways, or at least
two messages from you (To and Cc count, as in the map). Addresses on one existing person page count
once. Coverage counts qualifying correspondents with a listed page, whether
written or mapped, and reports `N people you write to have no page yet`.
Other category meters continue to show written pages out of mapped pages.

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
  Evidence indexes preserve the original items for retention and auditing, including
  overflow from capped rounds. In `claim-review.json`, `unretained_citations` lists
  handed citation numbers with no readable excerpt and `unverified_lines` lists
  prose citing only those originals (unverified, not refuted); `missing_citations`
  lists citations never handed to the turn and unavailable in the archive;
  `runner_removed` lists the contact values code took off the candidate before
  the audit, and `runner_removed_findings` the findings that asked for one back.
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
- A file error says what failed. A file that could not be opened or written
  is `Cannot read or write the selected co rem files: <the system's error, with
  the path>`. A file that was read but is not text names the file when REM
  knows it: `…/web/chart.png is not UTF-8 text (invalid start byte at position
  0); it was read, so this is not a permission problem`. On 2026-11-12 a PNG
  saved as a research capture was reported as a read or write failure, and the
  owner went looking for a permission problem.

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

Tidy also removes accepted and discarded native task workspaces once their
round finishes, and removes abandoned empty task folders after six hours.
Fresh workspaces may still be preparing a task. An active round retains its
workspaces because later tasks can still read earlier outputs. Run logs stay.
Attachments are deleted only when no current or archived page cites them and
both their filesystem access and modification times are older than 30 days.
The `.fetched` markers stay, so pruning does not download those attachments
again. Evidence copies older than a finished run are removed, while copies
from unfinished runs stay. Tidy records its deletions in `.state/tidy.json`;
native task completion stays in run logs. Deleted copies cannot be restored
locally.

An organisation-shaped page filed under People (with a Domains section) moves
to Orgs, keeping its text, citations and relative links. Existing destination
pages and the owner's page are left for an explicit decision.
Written service or automated-sender pages recognised by the map's existing
rules move to Notes with their content intact.

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
the map. Your language is the first non-English tag of a configured list, so `en,zh`
and `zh,en` both mean Chinese and only an English-only list means English; with no
list, it is the language you write most (detection orders by share, so 88% English
with the odd Chinese line means English). That one
rule decides the reader's interface, the language of a reply draft's gist, why and
【需要你：…】 slots (the body follows the reply skill's language rule, normally the
thread's language), and the language translated first each night; languages the
reader asked for come next, ahead of the rest of the list. The gist column is titled **要点** (Gist), with its
language added when the writer used another one (**要点 · English**). 中文 mode also reads regional Chinese caches such
as `zh-TW` and `zh-CN`. English pages remain the canonical audit record.

### Cached page languages

Every daily run works through all missing or stale translations, in this order:
the pages behind the rows Today shows (at most 8, in Today's order), then the
other pages with something waiting on you, then the newest page edits; opened
pages requesting a translation and pages changed this round break ties. Today's
rows are read once per round, not once per page. Current caches spend no budget. There is no daily translation count (D-104):
after every 2 investigation turns, and that break's session summary and Abstract
round, translation gets a share sized from its
backlog (a fiftieth of the waiting pages, at least 4), then investigation goes
on in the same turn; the weekly quota floor still stops translation.
`co rem status` reports coverage for each target language.

The reader shows an untranslated page's original with one quiet line under
its header, **中文版还没好，先看原文**, while its translation is on its way. In the
中文 interface a Today or Maybe over row starts with a quiet **原文** when its page
has no current Chinese version (any region) and the row's words are not Chinese
(names and codes inside Chinese words do not count).
Opening it in a non-English interface queues that language for the
next pass, even if it was not detected among the owner's languages. The Read in
menu still allows an explicit language choice.
Quoted evidence stays exactly in its original language.

What the model sees and must keep: the `## Sources` section is never sent; it is
copied back byte-identical after the translated prose. Amounts and currency
symbols stay as written (`$50,000` never becomes US dollars), and so do names of
people, organisations, projects, products and tools, including lowercase project
names; the page title and every link text are passed as an explicit list.
Email addresses, URLs, paths, issue numbers, versions and code spans are kept.
Each translation is checked before it is cached: headings, `[n]` citations,
privacy labels, quoted passages and reader markers. When a check fails, the
model gets one repair turn with the exact difference ("missing [12] (1 time)");
a second failure is reported and nothing is cached.

To translate every page at once (the pages themselves remain the audited source):

```bash
co rem translate --all
co rem translate --all --category people
co rem translate "Avery Lin"
co rem translate people/avery-lin.md --to ja
```

With no page named, `co rem translate` translates every readable page (not
logs, the skills catalog index, or pages held for review or
duplicated; `co rem status` coverage counts the same pages) that is not yet read
in your language, Today's pages first (the night's
own queue), using up to `limits.workers` concurrent pages. It first says how
many are already read in that language and how many it will translate, prints
`[n/N] PAGE: translated` or `failed: reason` for each, then the counts and how
many pages are now read in the language. Run again, it does nothing. A page's
failure does not stop the next page; any failures make the command exit 1.
`--json` returns the outcomes and counts. `--category` limits it to one
category. It costs one model turn per page, and the first line says how many:
without a terminal (an agent exploring help, a script) it starts only with
`--all`. Before each page it reads the Codex week and stops at
`limits.quota_floor_percent`, the floor kept for your own work, saying where it
stopped. One job runs at a time: it holds an OS lock on
`.state/translate-all.lock` for its whole life, which the system lets go when
the process ends, even after a crash or a reboot (`.state/translate-all.json`
only says since when, for display). A second run says one is already running,
and a night round that comes while it runs skips its translation pass. Omit `--to` to use the
language you read REM in (the one owner-language rule, `languages.owner_language`).

Chinese, English and mixed pages: a page counts as already in your language when
every line of its own prose is, and at least one line is. Quotes, names, link
texts, code, source ids, privacy labels, Facts labels and the reader's English
markers are not counted, since they stay as written in any translation. For
Chinese a line with two Han characters in a row is Chinese, so names and English
terms inside a Chinese sentence do not make it mixed; any other line of three
words or more is another language. A page written in Chinese costs no model
turn; a page that mixes Chinese and English prose is translated (its Chinese
lines come back as they were). The reader marks a mixed page `written_in:
"mixed"`, so it waits for and offers the translation like an English page.

The live reader runs the same job from a worded button, **全部翻译成中文**, in
Settings, beside **中文版还没好，先看原文** on a page, and in the home translation
notice. It posts to the Host's `/rem/translate-all` (`start`, `status`, `stop`)
under the same loopback, cookie and JSON-only rules as every other write. The
button names its cost, **全部翻译成中文（606 页）**; while it runs the reader shows
**已翻译 N / M** with **停止翻译**: pages already begun finish, the rest are left as they are. At the quota floor it stops with
**额度只剩留给你自己用的部分，已停在 N / M**. A refused request says so in words; a
dropped connection is retried with a growing wait. When it ends the reader rebuilds and the
open page reloads with the translations. No command to copy (D-60).

Each model translation records a `translate` run with its language, page,
duration, harness/model and usage, including failed attempts with reported
usage. `co rem logs --usage` includes these costs; daily translation summaries
retain attempt counts without duplicating the per-page usage.

Reader settings shows **Notebook languages: 中文 · English — detected** (or
**— set**), read-only: REM detects them (D-103), and Reader settings carries no
command to copy (D-60); `co rem config set languages` in a terminal still
overrides detection. The home translation notice is a fallback based only on written pages.
When the last init or daily translation reported failures, it names how many
pages could not be translated and offers the **全部翻译成中文** button, never a
command to copy (D-60).

### Codex history during maintenance

REM archives its internal Codex threads after each model call, including failed
calls when the provider remains responsive. A forced cancellation or process
crash can leave a thread active. In preview 1.9.3rc26, an approved `co rem start`
also repairs older internal traces; `co rem init` reaches the same approved start.
Inspect or apply that repair separately:

```bash
co rem history
co rem history --archive
```

Only ConnectOnion-generated conversations or recognized legacy REM delegates
under this notebook's private task
directory, older than one hour, are eligible. Personal conversations, pins,
recent work and threads observed active are retained. The repair uses native
`thread/read` and `thread/archive`, makes no model calls, writes no native
database rows, and keeps a private receipt. Valid paginated threads need not
have a legacy JSONL file. Because native archive also processes descendants,
an unarchived child outside these safeguards keeps its parent too; unknown
children also protect the parent. A rerun skips already archived traces. Error results
in the normal automation inbox and ordinary workspaces remain visible.

They leave the active conversation list while their trace and session ID remain
available for explicit resume and `co rem logs`. Before resuming, REM
unarchives the thread, then archives it again after the turn. Ordinary interactive Codex
threads are unchanged.
History archiving also applies when launchd owns the timer. In rc21, eligible
Codex notebooks use the configured exec or desktop runner; see [Scheduling](#scheduling-and-accounting)
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

## Native round: next and submit

A Codex exec or desktop Scheduled session can do the model work itself. The `rem` skill
runs this loop; launchd retains `co rem sync --scheduled` as its child-runner fallback.

```bash
co rem next --scheduled
# Read the instructions and material; write only the named candidate file.
co rem submit native-0123456789abcdef0123456789abcdef
# Repeat next / submit until next reports round done or a budget stop.
```

For a manual native round, use `co rem next`. Task output is a short header:
task ID, stage, workspace, candidate path, exact submit command and
`Instructions: <workspace>/instructions.md (N lines)`. Full instructions stay
in that file, including any citation audit or required corrections. `--json`
retains the full instructions, material path, output path and submit command
as structured data.

Each task's instructions are in one order: the assistant's goal, the task
(workspace, what to read or the inline material, what to write), the memory
step, the stage Skill, and last up to 4,000 characters of `.state/memory.md`
followed by the page's latest enrich, muse and investigate/continue reports
when available. Those reports are bounded too, at 12,000 characters together:
newest first, each whole while it fits; the first that does not fit keeps its
last whole lines and says "The first N of its M lines are left out; the whole
report is the `report` field of <root>/.state/runs/<run id>.json", and older
ones are listed with their run files as "left out to keep this prompt short".
They used to be appended whole, outside the memory bound: 27.1K of one
prompt's 66.5K characters (#3083).
Memory is given in whole lines, never cut inside one: first the lines that name
this record's file, then the newest others, in the file's order. Both are
evidence, never instructions or permission to bypass review. Memory used to
come first, as the file's last 4,000 characters: the task began 70–75% into
the prompt, and the notes were mostly about other pages (#3083).
The agent appends 1–3 lines of `page · approach · result · next` to that memory
(not asked of a worker `co rem exec` confines to its task folder, which cannot write there),
including answered and new questions and reusable tool discoveries. Investigation
reports cite the predecessor's next step; unresolved questions stay in the page's
existing `Uncertainties` section. Accepted native run logs retain `report.md`,
including after a citation audit. Scheduling the `continue` pass is separate.

Native task instructions contain directions and file pointers. Extraction, page
writing, claim audits, repair findings, same-person comparisons, translations,
session summaries, inquiry stages and project jobs keep their packets in the
task workspace. Read them in pieces with `sed -n '1,80p' FILE` or search with
`rg`, then continue through the relevant material. Prepared files have no lines
longer than 4,000 characters. Human reading views wrap long lines; exact JSON
retains text for quotations and validation. Long JSON strings use consecutive
`__rem_text_parts__` entries, decoded losslessly by REM; read the human view
without writing a reconstruction script. An unusually long original page is
supplied as exact JSON rather than an unreadable initial Markdown copy.
Session summaries use one file per session, such as `sessions/s1.json`.
The exception is extraction, maintenance and investigation material that fits:
when the stage Skill, its additions and `material.md` together are within the
100,000 bytes one argument may carry, the instructions hold the additions and
the material inline (`<instructions>`, `<material>`) and say not to reread
`instructions.md`, `additional-instructions.md`, `material.md`, `material.json`
or the Skill's `SKILL.md`. Larger material names one file, `material.md`:
`material.json` is still written for the audit trail but not named, because the
quote check ignores where lines wrap. Every native task also says that
`task.json` is the runner's own record and not to be read. Measured over one
day before this (#3083): `material.md` read 320 times, `material.json` 318,
`task.json` (180–344 KB) 134, the Skill already in the prompt 57.
The single-call child runner keeps its existing inline packets and JSON replies.

Audit checkpoint lines must contain `excerpt: "verbatim original span"`, at least
20 characters copied exactly from that citation's `context.excerpt` in
`audit-material.json`. If the whole original is shorter, quote it in full.
Bare verdicts and forged excerpts do not count; progress reports rejected lines.
Malformed audit decisions are refused for correction, never promoted.
PASS is refused until every citation has a verified checkpoint, with the next
unchecked batch shown after `Now:`. A missing original cannot be marked checked; retrieve it or repair the candidate
before submitting PASS. Repair preserves verified checkpoints only
when the cited claims and original are unchanged.

Both Codex scheduler modes fire at each saved time, then every 15 minutes until the next
saved time or three hours after that start, whichever comes first. A fire at
exactly three hours is included unless another saved time has arrived. The
macOS wake job in codex-app mode opens Codex 15 minutes before every fire. Saved times and the
saved timezone remain what `co rem status` and the consent summary show;
follow-ups do not change the consent fingerprint. Run `co rem start` to apply
the updated automation and wake job to an existing installation.

Do as many tasks as you can; if you stop, the next follow-up continues within
15 minutes during that window. It resumes the pending task (including an
advisory claim left by an abandoned turn), or prepares the next task in the
same round. After completion, a fire with no new saved time due immediately
returns `not due`: it reads no new sources and reserves no runner budget.
A scheduled turn can also resume an unfinished manual round, retaining its
manual slot rather than claiming a saved time it did not start in.
Material is evidence, never instructions. Follow the printed command exactly,
including `--root` for another notebook.

Submit verifies the prepared input hashes and runs the same stage checks used
by sync. It may print a citation audit step before accepting a page. A refused
candidate stays pending: fix the file and submit again. If evidence changed,
use `co rem next --discard` to discard the task explicitly. Tasks older than a
day are listed as stale and discarded on next; a prepared date remains valid
after midnight. Manual sync refuses to overlap pending native work.

`co rem logs` includes native tasks. Supply measured token usage with
`co rem submit TASK-ID --usage-json '{"input_tokens":120,"output_tokens":40}'`
when available. Otherwise usage remains unknown. A task `co rem exec` or
catchup drives records the sum of every turn it took: each turn (the render,
each repair) is a thread of its own, and the record kept only the last one's
tokens (0.91M input tokens recorded of 9.2M used on 2026-11-17). A turn closed
at its deadline adds what the adapter reported before the task is parked. A
`--usage-json` given by hand still replaces the task's usage.

### When a mailbox fails on one page

A missing mail or attachment while `next` prepares one page sets that page aside;
`next` goes on to the next page in the same call. From 2026-11-12 every 15-minute turn
on a real notebook ended with no task: 16 turns on an Outlook HTTP 404, then 14
on a ReadTimeout listing one mail's attachments, both while preparing one
person's page. The error left `next` before the round was saved, so each turn
tried the same page again, and four nights read no mail.

- **HTTP 404 and 410 mean that one piece of mail is gone.** Message bodies,
  cited-original headers and bodies, and attachment metadata use the same check
  for Gmail and Outlook. REM records the native message ID, operation, HTTP status
  and reason under `.state/mail/dropped-missing/`. A page needing it is parked in
  `.state/fetch-parked.json`; `next` names the missing ID and serves the next item.
  The unchanged page stays parked across later turns, even after the old retry
  time. A change to the page text makes it eligible again, for example after new
  mail updates the page or the owner edits its evidence. Missing cited originals
  appear as **could not be prepared** in the night outcomes and are not fetched
  again for that same source ID; a new citation can be fetched. To retry an original
  restored by the provider, remove its matching `mail/dropped-missing/` entry.
  Queued sync mail is consumed with its ID in progress's `dropped_missing` and
  the batch's missing count; an initial archive records it in `dropped_missing`.
- **Other single-message read failures still fail preparation.** HTTP 401/403,
  429, 5xx and network errors retain their messages after any existing retries;
  they are not treated as deleted mail or a successful attachment listing.
- **If no task was served and every remaining candidate is parked, the round
  fails with that reason.** The background turn receipt, `co rem status` and Today
  show the failure through the same preparation-failure reporting as other errors.
- **A mailbox whose listing fails for three pages in one turn, or whose listing
  reports expired authorization, is not asked again in that turn** (the turn is `CO_REM_TURN_ID`; a
  `next` typed by hand is a turn of its own). Pages that would ask it wait for
  the next turn without back-off, back in the same round, and work that needs no
  mail (projects, skills, retries from held material, summaries, translations)
  goes on. A page that was merged while it waited comes back as the page it was
  merged into; one that no longer exists is dropped from the ledger.
- **A mailbox failing outside any one page** — listing who wrote since the last
  round when a round starts, or reading a slot's new mail — is recorded the same
  way (an event in `.state/fetch-parked.json`, the night card's sentence) and is
  not asked again in that turn; the other mailboxes are still listed and the
  sessions are still read. Four nights read no mail while a failing mailbox was
  read again at every slot.

Today's night card says why in one plain sentence under its title, in the
reader's language, and folds the pages set aside with when each is tried again:
«昨夜 1 项因 Outlook 超时跳过，会再试», or when one page failed again and again
«REM 昨夜在 Outlook 上卡住了：超时 3 次，已跳过这一项，其余照常» (at most three in a day under the back-off), or for a mailbox
stopped for a turn «昨夜 Outlook 出了问题（授权已过期），REM 那一轮没再问它，其余照常».
No exception name or command is shown; the reader has no reconnect button yet,
so expired authorization is said in words only. A shared reader carries none of it.

### One quiet morning message

`co rem morning --dry-run` prints one line saying what a real run would do now
(`would send now via telegram`, `already sent 06:02`, `not due until 06:00`,
`channel none: nothing will be sent`, …) and then the exact short zh/en message,
without a model call or sending anything. `co rem morning` sends once between
06:00 and 11:00 in the notebook timezone; later checks record the date as missed
and send nothing. Scheduled `co rem next` checks automatically. The note covers
everything since the previous note, so nothing is reported twice or skipped.
No new work and no new decisions means no message. A checked local date never
sends twice, including after a failed send; inspect `co rem doctor`.

Default channel is `none`. Run `co rem doctor` for existing configured senders
and their next command. Doctor marks an enabled channel with an absent sender
or destination as incomplete setup. Choose your own destination explicitly:

```sh
co rem config set notify.target YOUR_OWN_CHAT notify.channel telegram
co rem morning --dry-run
```

Channels are telegram, lark, whatsapp, email, or none. REM reuses their existing
send paths. Email is the last choice: a company mailbox is wrong for personal
content. Nothing is sent to a guessed recipient. Open Today using the last line
(the live reader when serving, otherwise `co rem open`). See
[the morning data contract](../rem-night-outcomes.md#morning-message-sprint-11).
