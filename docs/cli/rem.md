# co rem — current branch contract

Updated 2026-10-02. co rem ships in the opt-in 1.9.0 previews and becomes
long-term supported in 1.9.0 (#1664 names it first). The command surface and
every `--help` page are the agreed design in #1656; the pages themselves live
in `connectonion/cli/commands/rem_help.md` and a test holds them to the code.
Old command names (`unfinished`, `people`, `daily`, `subscribe`, `subscriptions`,
`unsubscribe`, `route`, `usage`) still work until 1.9.0 and print their new name.

See the [2026-09-17 progress review](rem-progress.md) for the feature inventory,
current CI blockers and remaining work.

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
through the login you choose. By default it runs on your own Codex plan and
spends no OpenOnion credits.

What it costs, measured: the first run writes 12 pages at a time. On a real
notebook it wrote 198 of 242 people, project and organisation pages in about 25
minutes, and it stops starting pages at 60 points of your Codex week.
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
co rem start                # Keep it current: approve sources, turn on the daily round
```

The first run is one command (#1943). `init` first maps 90 days of
mail and your local Codex / Claude Code sessions, saves the private mail
material, and prints your own page's facts — who you write to most, how much
mail, which projects you have been coding in — with the page's path, within the
first minutes. Then it uses the configured model to write your own page: the whole
`investigate me`, from everything you sent and your coding sessions of the last
30 days (or `--days`), one model turn over evidence files, about 15 minutes.
It writes a quick first pass of your page in about 4 minutes, then the whole
page alongside the selected pages. Next come eligible people, those active in
the last 14 days first, each investigated from up to two years of their mail;
queued projects already listed in the map, recent first; organisations linked
to those people; and installed skills from source and retained run evidence:
12 pages at a time. Session folders discovered after the map summary remain
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

Before it spends anything it says one total (#2008): which runner and model,
that it runs on your own plan, and "About N pages (...), ~X billed input tokens,
~Y minutes (an estimate ...)". Per page it is the median of this notebook's own
completed runs of that kind (`.state/runs/`); before there are any, defaults
measured on a real 7-day first run on 2026-10-02: each owner turn 768k and
~4.5 minutes (quick and full are both counted), a person 304k and ~2 minutes
with up to two years of evidence, a project 69k and ~1 minute, an organisation
129k and ~2 minutes. Minutes are wall clock: after the quick owner turn, the
full turn and selected pages share up to 12 workers. The estimate simulates
that queue so a slow last page is not hidden by an average. Roughly 35% of a weekly runner
allowance is a target, not a hard stop. The selected investigation finishes
even if it uses more, unless the configured weekly safety floor is reached;
pages already in flight finish. Ctrl-C stops it, says which pages
were written, keeps the map and every page, and names the command that
continues. It skips the model steps, with a one-line reason, when
the runner is not installed or not signed in (checked before the map starts,
without a model), when no mailbox gave an address of yours, when your page was
already written. `--json` and non-terminal runs investigate by default too.
`--no-investigate` explicitly builds the map only. Older
projects wait for `co rem projects write`; more people for
`co rem investigate people`.

Your page is titled with what you are called: `--name` if given, else the
name the people writing to you put on your address (the To and Cc of mail you
received; spellings that differ only in case are one name, and a name that is
just the address, `xietianle`, is not one), else the From name of mail you
sent, else the name a mailbox has configured (#2008). On the owner's real
account the configured name was "Aaron x", and Outlook stamps it on every sent
mail too; correspondents wrote "Aaron Xie". A new notebook names the file after
you (`people/aaron-xie-….md`); an existing page keeps its path.

Progress is one line per stage (updated in place in a terminal); every step is
kept in `.state/init-progress.log`. Addresses that look like yours (you wrote,
nobody replied) are listed on one line with one command that confirms the ones
you keep: `co rem init --mine a@example.org,b@example.org`. Mailboxes init read
are subscribed, so `co rem start`'s summary lists them as sources to read; start
still asks before anything is read in the background.

To fill other pages, `co rem investigate` lists what is left, by category, and
runs no model. Copy the `Next:` command printed by `investigate` to investigate one existing
page. You can also supply an exact title or email when it identifies one page,
for example `co rem investigate 'Ody'` if that person exists in your notebook.
Ambiguous names list the matching paths and do not start a model. Example page
names in old help text, such as `people/emma.md`, are not built-in records.
`--help` displays help and exits, even when you also supply a page name.

```bash
co rem investigate          # What is left to investigate, by category; no model
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

`start` explicitly authorizes collection and installs background maintenance
plus at most one unfinished-page investigation per local day when the day's
call budget allows;
`init` does neither. A mapped page is not an investigated or quality-approved page.
For an initial trial, `co rem init --days 5` investigates your page over the same
five-day window. `investigate me --quick` is the older bounded pass: it samples
recent evidence, takes one synthesis turn, and marks its coverage as partial.
init no longer uses it, since #1850's evidence files let one turn search
everything you sent.

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

The [co rem CLI reference](../../connectonion/useful_skills/rem-init/CLI.md) explains
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
| `co rem init` | Discover sources and map pages, then use the configured model to investigate your page, eligible people, queued projects, related organizations and installed skills, recent first. `--no-investigate` explicitly stops after the map. |
| `co rem scan people --days 150 --min-mails 1` | Enumerate correspondent signals from Gmail/Outlook; no model. Repeat `--mine <address>` for own addresses. |
| `co rem scan orgs --days 180 --min-people 2` | List work domains that two or more people write from — where an organisation page earns its place. No model. |
| `co rem scan projects --days 150` | Enumerate session working directories and local Git repository identities; no model. |
| `co rem stub person "Alice" --email alice@example.org --handle 艾丽丝` | Create the canonical person skeleton if absent. |
| `co rem stub org "UNSW" --domain unsw.edu.au --person people/vern-chan.md` | Create an organisation skeleton; `People here` holds links, not copies. |
| `co rem stub project "Aurora" --path /path/to/repo` | Create a project skeleton. |
| `co rem list people --aliases` | Existing identity roster: page, title, aliases, addresses, relationship summary. |
| `co rem list people --review` | Pages held for review: titled by an address the owner never wrote to, or only ever wrote to. |
| `co rem investigate people/alice.md` | Read the existing page, gather sources, digest oversized material, fill that same page through the Skill. |
| `co rem investigate` | What is left to investigate, by category, most useful first. No model. |
| `co rem investigate people --limit 3` | Investigate the next three people, the last 14 days' correspondents first (`--recent-days`): a person investigated before reads only the mail since then ([details](rem-people-pages.md)). `--list` prints the order and the cost and runs nothing. `projects`, `orgs`, `skills` take unfinished pages, most mail or sessions first. |
| `co rem investigate me` | Fill your own page from what you sent and your coding sessions of the last 30 days. |
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
| `co rem open --live` | Open the live view in O Chat, read from your `co ai` Host over OIP. Checks first that the Host is online; if it is not, says so (start it with `co ai`) and opens the snapshot instead. Default notebook only. |
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
"not investigated yet"), **Some findings** (written content, no investigation
pass yet) and **Investigated**. "Unknown" lines and placeholders are not shown;
the headings still empty are named once at the foot of the page with the
`co rem investigate '<page>'` command that fills them. Lists put pages with
findings first, then newest last contact. The Markdown file is unchanged, and
**Copy Markdown** at the foot copies it as written, unknowns included.

### What the reader shows (1.9.0a13 preview)

The reader returns the context REM carried forward, then helps you recall an
older page before showing its answer. It remains a point-in-time snapshot.

- **Home** opens with up to three pages changed in the latest pass, labeling
  their statements as current context. When the new run log has cited Facts or
  Contact value changes, they appear separately as old and new values. A page
  rewrite alone is not described as a new fact. **Remember with REM** asks
  about an older page and reveals what it says on request. **Open threads**
  previews three items in each direction and links to the full action view.
  **This week** follows. Compact category cards replace the long contents
  shelves. The last pass's counts and hypnogram are available in **How REM
  processed the last pass**. The owner's page is pinned as **You**.
- **People, Organisations and Projects** open as a sheet: one row per page,
  the facts in columns (people: what's open next to the name, then company,
  role, email, phone, last contact, mails; status is the moon beside the
  name), a sticky header, sort on any column, filters (*Something open*,
  *Yours to answer*, *Written*, *Mapped only*) and a text filter. A row opens
  the page. It fits 1440 px; narrower, it scrolls inside itself with the cut
  edge shaded and the name column held. The columns come from the notebook's
  index (`store.people_table`, #2067) when `.state/rem.db` exists, embedded in
  the snapshot; before it does, from each page's Facts and the map's mail
  counts (`index_rows` and `mail_facts` in `reader.py`, `facts()` in the page).
- **"You", not "the user"**: pages are written about "the user"; the reader
  says "you" ("you have not signed it", "How you write to them") at render
  time only, so the Markdown and Copy Markdown keep the words as written.
- **A page** opens on a focused status, next exchanges, compact facts, related
  records and filterable dated Activity. Project pages add purpose and a
  recorded decision when supported. Explicit links and unambiguous name
  mentions make cross-page cards and backlinks; their labels distinguish a
  link from a mention. The original prose, every Facts/Contact field,
  Insight, History and Sources stay under the always-visible **Full memory and
  sources** section. A claim
  number `[n]` opens its source description and, when locally archived, an
  original excerpt. Cited conversations show up to twelve recent archived
  messages with the total count. Missing original bodies are labeled, never
  replaced by a generated summary. A page only mapped from metadata says so
  and gives the command to investigate it.
- **Open threads** shows all supported obligations with direct record links.
  **Memory changes** keeps cited field changes separate from page rewrites.
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
focus is visible, and the only motion (the hypnogram drawing in) is off under
`prefers-reduced-motion`.

To see every view on an invented notebook, light and dark, desktop and phone:
`python scripts/capture_rem_reader.py OUT_DIR` (the fixture is
`tests/fixtures/rem_reader_notebook.py`; `--root COPY` renders a copy of a
real notebook, and those screenshots stay local).

`init` is the foreground Skill workflow. `start` remains the explicit
background lifecycle command; initialization does not install a schedule.
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

launchd invokes the resolved `co rem --root ... sync --scheduled` CLI every
five minutes, with PATH entries for co and installed delegates. Saved local
time slots determine whether a batch is due. Repeated start reloads one job;
missed slots coalesce into one catch-up. No permanent co rem daemon is added.

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
- **A run the meter cannot see is counted from its tokens** (#1990). Codex
  reports whole percents, and on the 1.9.0a7 acceptance notebook the week read
  29% before and after every run, 3.4M input tokens in all, so the budget said
  "0 of 10 points" all week. A run whose reading did not move (or could not be
  read) now counts `(input − cached input + output) / 1,000,000` points, to one
  decimal: about a million tokens the model had to read fresh or write is one
  point. A run that did move the meter counts what the meter says.
- **Scheduled and manual investigation has a weekly budget**, `limits.investigation_quota_points`,
  default **35** points of the weekly window. The
  scheduled round adds up the points its investigation runs used since the
  window last reset, and starts no new page once that reaches the budget.
- **The initial investigation uses a soft 35% target.** It finishes the
  selected pages beyond that target and the normal investigation
  budget. The configured safety floor still protects the rest of the week.
  Claude Code and other runners without a readable weekly meter show an
  estimate and finish the selected cohort; the CLI cannot claim to have
  measured 20% of their plan.
- **Manual investigation counts too** (#1842). `co rem investigate PAGE`,
  `me` and CATEGORY runs record the meter like the round does, and their
  points count toward the same weekly budget. A CATEGORY run stops starting
  pages when the weekly budget is spent, when its own `--budget N` is spent, or
  at the floor, and says which; the page in flight finishes.
- **After init**, `co rem investigate all --budget 10` works whatever init left:
  one queue over people, projects and organisations by weight (the same order
  the round uses), until 10 points of the week are spent. `--list` shows that
  order without running a model.
- **A floor protects your own coding.** No investigation page starts once the
  week is at `limits.quota_floor_percent` or more, default **90%**, however much
  of co rem's budget is left. co rem shares this quota with your real work.
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

The scheduled daily round maintains first. The first run of the local day then
investigates unfinished pages, most recent activity first, within a reserved
share of the daily attempt cap (8 calls; a person is one investigation); every later run
updates only the people with new mail and the projects with new messages since
the run before, at most 5 pages. Both stop at the weekly budget or the floor and
record how many pages are left ([details](rem-people-pages.md#the-daily-round-four-runs-two-jobs-1723)). Initialization maps sources first, then runs a model investigation of the selected pages; manual
investigation remains outside the scheduled cap.

The UI is a static snapshot of the notebook as it is now; run `open` again to see later changes (`--no-launch` says so and ends on `co rem open`). No merge,
release, new background job, broad mailbox backfill or production co rem rewrite
is implied by the architecture refactor.

See [acceptance evidence](../testing/rem-acceptance.md).

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

Counts describe observed invocation attempts, not proven starts or lifetime runs.
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
co rem open
```

This lists 90 days of mail by default: correspondent metadata plus the short
preview the provider lists with each message. A seven-day window that fills the
provider's 200-message listing cap is split until every message in it is
listed, so a busy week is no longer cut off at 200 without a word. Init does not
install a schedule. It subscribes the mailboxes it read, so `start` offers them,
but nothing is read in the background until `start` is approved.

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
to that one person ("Hi Larry,", "Larry 你好，", "子明，"). A greeting to several
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
insight, and on Ody's page the phone number could not be found at a glance. A
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
- Every value carries a citation, except `Email`, `Handles` and
  `Also known as`, which the map fills from the addresses it found. A citation
  at the end of a line covers the uncited values before it
  (`UNSW Founders; [UNSW](../orgs/unsw.md) [12]`); a full stop after it is
  ignored. A new value with no citation is taken off the page when it is
  saved (`review.json`: `facts_uncited_dropped`) rather than refusing the page.

`facts.parse(page)` returns `{"Phone": [{"value": "+61 2 5550 0142",
"qualifier": "work", "citations": ["1"]}, …], "Location": [], …}` (an empty
list is `Unknown`), so the reader, the People table and a later database
(#2067) read the same thing. A page written before 1.9.0a9 has `## Contact`
instead: `facts.upgrade` renames it and adds the missing labels as `Unknown`
the next time an investigation or maintenance writes the page; `facts.parse`
reads either.

### Extracted before prose

Before the model turn, `connectonion/rem/fact_extract.py` reads the gathered
material with no model: the subject's own addresses, phone numbers in their
signature blocks (with `work` / `mobile` from the line's label), LinkedIn
links, the dates of the first and last message, the signature block itself,
the lines of calendar invitations that name the subject, and the company domain
when it is not a mailbox provider. They go to the turn as the
`investigation:facts` item, each with its source id, even when the rest of the
material is in files to search — the turn confirms them, extends them and
cites the source id, not the item.

The model may correct a fact the material contradicts; it may not lose one.
After the turn, a phone, address, LinkedIn link or contact date the extractor
found that appears nowhere on the page is put back into its field with its
source (`review.json` lists it under `facts_restored`). Company and role from a
signature are context, not restored: reading a title off a signature is a
judgement.

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
Ody 6, Tamara 7, Richard 6, the owner's own page 3. The material held more
than each page had: Ody's phone (in a signature), every page's first and last
contact, and on the owner's page a phone, links, company and role. After
re-investigating with these skills, Ody went to 8 (9 with the restore step over
the full window; the run was a quick pass of the newest mail) and Tamara to 11,
her mobile among them, each with three labelled Insight lines.

When an investigation finds nothing new, the restore step still runs: a page
whose cited mail carries a phone the page lacks gets it back with no model call.
In a quick pass (`--quick`), the extractor sees only the sampled mail.

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
inspect a bounded set of files in the page's recorded local Paths; the file
inventory is a lead, not proof of file contents. Review the candidate and its
citations before treating it as a verified notebook page.
Completed extraction chunks are checkpointed under `.state/extracts/investigate/`;
rerunning the same evidence and model settings can reuse them after an
interruption. The running log records the current chunk and usage from completed
chunks. A changed source or extraction prompt invalidates the checkpoint.

Repeated mapping refreshes generated project counts, dates and paths while preserving written notes. Skill pages retain authored descriptions and show current installed metadata in a separate managed section. Unchanged content is not rewritten. Equivalent SSH/HTTPS Git remotes share an identity; distinct case-sensitive repository paths remain distinct. Search groups skill installations just like the catalog, and the homepage labels its content as a snapshot rather than claiming every skeleton is maintained.

## Reflections, review and staged investigation

See [co rem memory workflows](rem-memory.md) for `reflect`, `review`, `capture`,
`route` and `daily`, including provider, retention and budget limits.
