# co rem help pages

Each section is printed verbatim by `--help` for the command it names.
The agreed design is issue #1656; change a page there and here together.

## co rem

```
co rem — a notebook about the people, projects and tools in your work, kept up to date from your mail and coding sessions.
Experimental: a preview; its commands may change before 1.9.0.

Build (once)
  init          Build the notebook from 90 days of mail and sessions, then write your page.
  investigate   Fill a page, a whole category, or your own page, using a model.
Read
  open          Browse the notebook in your browser.
  list          List pages in a category (people, projects, orgs, skills).
  show          Print one page.
  search        Find text across pages. No model.
Keep it current
  start         Approve sources and turn on the daily schedule.
  stop          Turn the schedule off. Pages and approvals stay.
  status        Is the schedule on, when it runs next, what ran today.
  sync          Run one update now.
Settings
  sources       Which mailboxes, coding tools and chats the notebook reads.
  config        Model, schedule times and limits.
  logs          What each run did, and what it cost.
  doctor        Check that everything the notebook needs is installed.

Options (before the command):
  --root DIR    The notebook folder (default ~/.co/rem).
  --json        Machine-readable output: {"ok", "data", "next"}.

First time:   co rem init
Example:      co rem search "term sheet" --in people
Every page:   co rem <command> --help
Advanced:     co rem advanced --help   (scan, map-skills, stub, reflect, reflections,
              propose, review, abstract, capture, projects)
Old names:    unfinished, people, daily, subscriptions, subscribe, unsubscribe, route
              and usage still work until 1.9.0 and print their new name.
```

## co rem init

```
Build the notebook and investigate what matters now. One command.

First the map is made without a model: a page for each person you write to, each organization,
each coding project and each installed Skill, plus your own page, titled with your
name and filled with who you write to most and where you work. init prints that
page when the map is done. It lists 90 days of mail headers, the preview line your
provider lists with each message (to name people by your greeting), saved
contacts, and session metadata, then saves a private copy of each listed message
body, once, so investigating a person later reads it from disk.

Then it writes your own page by itself from everything you sent
and your coding sessions of the last 30 days (co rem investigate me): a quick
first pass in about 4 minutes, then the whole page alongside the rest. It also
investigates eligible people, those active in the last 14 days first (at least two
years of their mail, back to the first mapped message when older), projects
(recent first), organizations linked to those people,
and installed skills from their source instructions and retained run evidence,
12 pages at a time. The result should let you recognize useful relationships
and work immediately, with evidence cited on each page.
--first-people, --first-projects, --first-orgs and --first-skills cap a kind (0 for none).
Before the first page it says one total: about how many pages, ~how many billed
input tokens on your plan and ~how many minutes, an estimate from the median of
this notebook's own runs (before there are any, measured defaults). It names the
runner and model. Around 35% of a weekly runner allowance is a target,
not a hard limit: the selected investigation finishes even if it uses more.
The configured weekly safety floor still stops new pages when measurable.
Ctrl-C stops it, says which pages were written, and
keeps the map and every page. It is skipped, with the reason, when the runner is missing
or signed out, when no mailbox gave an address of yours, or when your page was
already written. More people: co rem investigate people. More projects: co rem
projects write.

Usage:    co rem init [--days N] [--mine ADDRESS[,ADDRESS...]] [--name NAME] [--mail gmail|outlook]...
                       [--no-mail-archive] [--investigate | --no-investigate]
                       [--first-people N] [--first-projects N] [--first-orgs N] [--first-skills N]
Example:  co rem init --days 90 --name "Aaron Xie" --mine aaron@mail.openonion.ai,aaron@openonion.ai

Inputs:   Connected mailboxes (co auth google, co auth microsoft) and local Codex /
          Claude Code sessions. --mine adds addresses that are yours (commas, or
          repeat it). Addresses that look like yours are listed on one line, with
          one command that confirms the ones you keep.
Options:  --investigate     Explicitly request the default investigation.
          --no-investigate  Build the map only.
          --first-people N    Cap eligible people (default all selected; 0 for none).
          --first-projects N  Cap queued projects (default all selected; 0 for none).
          --first-orgs N     Cap related organizations (default all selected; 0 for none).
          --first-skills N   Cap installed skill investigations (default all mapped; 0 for none).
Output:   Your page's facts and where it is; one progress line per stage on stderr
          (every step in .state/init-progress.log); pages under ~/.co/rem (or
          --root); private files under .state/: source-inventory.md and .jsonl
          (what was listed, window by window), and mail/ (one body per message,
          per-person and per-project indexes). A seven-day window at the
          200-message listing cap is split until all of it is listed. Mail bodies
          never go into a page and never leave this machine. Re-running keeps
          anything written and reuses saved bodies.
Effects:  Writes pages and private files (owner-only). Reads mail bodies unless
          --no-mail-archive. Mailboxes it read are subscribed for the daily round;
          nothing is read in the background until co rem start is approved. The
          map costs nothing; the subsequent investigation uses the configured
          model for the selected people, projects and organizations. No schedule.
Takes:    About 10 minutes to map 90 days of two mailboxes; saving bodies takes
          longer; investigation time depends on the selected pages and runner.
          An interrupted run resumes where it stopped.

Next:     co rem open   (read your page), then co rem start (keep it current)
Back:     co rem --help
```

## co rem investigate

```
co rem investigate — fill pages from everything about their subject, using a model.

A page is filled only from what it was given. The new page replaces the old one
only if every citation points at a message, file or URL the run supplied. A
refused page is kept, with the reason, so the model's work is never lost.

Usage:
  co rem investigate                          List what is left to investigate, by category. No model.
  co rem investigate PAGE                     Investigate one page.
  co rem investigate CATEGORY [--limit N]     Investigate the unfinished pages in one category,
                                               most useful first. Default --limit 5.
  co rem investigate me                       Investigate your own page from your recent work.
  co rem investigate me --quick               Bounded first pass; says what it did not cover.
                                               init runs this for you in a terminal.
  co rem investigate all --budget 10          The whole queue, highest first; stop new pages after
                                               10 Codex-week points are spent.

  CATEGORY is one of: people, projects, orgs, skills, all (people, projects, orgs and skills
  in one queue, by weight)

Examples:
  co rem investigate
  co rem investigate people/ody-zhou-c6a901ffd8.md
  co rem investigate people --limit 3
  co rem investigate people --recent-days 7 --list
  co rem investigate projects --list          (show the order, run nothing)
  co rem investigate all --list               (the whole queue's order, run nothing)

What each kind reads:
  people    Every message to or from their addresses, searched on the server, with
            readable attachments; coding sessions that mention them. A person
            investigated before reads only the mail since then.
  projects  The coding sessions run in the project's folders, and the project's own files.
  orgs      Mail on the organisation's domains; primary correspondence from shared
            contact candidates on other domain pages, with identity left to verify.
  skills    Installed source and recorded runs (co eval results; --eval-dir to choose where).
            A model writes a cited page; the skill itself is never executed.
            Missing runs remain unverified; invocation counts are not successes.
  me        Your own sent mail and coding sessions from the last --days (default 30).

Options:
  --days N       How far back to read (730 for a full page; 30 for me; updates since last run)
  --quick        With me: sample recent evidence for one model turn; explicitly partial
  --limit N      With CATEGORY: at most N pages this run (default 5; 0 for all)
  --list         With CATEGORY: print the order and stop; no model
  --recent-days N  With people: people written to in the last N days first (default 14)
  --budget N     With CATEGORY: stop starting pages once this run has used N points of
                 the Codex week (1-100). With --budget, --limit defaults to 0 (all).
  --handle TEXT  PAGE only: another address or name for the subject (repeatable)
  --eval-dir DIR skills only: where the run records are

Order within a category: pages still marked Unknown first, then those with the
most mail or sessions. A page investigated in the last 7 days is skipped. Your
own page comes first until it is investigated (investigate me). People: those you
wrote to first, then those who wrote more than once, then one-mail contacts; in
each, the last --recent-days first, then most mail for its age. Automated senders
are left out. Mail counts are the map's, a floor for what is read. A person
investigated since their last mail waits for new mail, then reads only that. A
run that finds nothing about its subject stops before the model and leaves the
page unmarked.

Budget: with the Codex runner every investigation records your Codex week before
and after, and counts toward investigation's weekly budget (limits.
investigation_quota_points, default 35). A CATEGORY run stops starting pages when
that budget is spent, when --budget is spent, or once the week is at
limits.quota_floor_percent (default 90%), and says which. Pages already in
flight finish, so --budget is advisory and can be exceeded by in-flight pages.
Without a meter (another runner, Codex signed out), --limit is the bound.

Effects:  Reads message bodies and files. Calls the model configured in co rem config:
          one call per page. Material too large for one turn is written to evidence
          files the model searches, not summarised first; files are removed after the
          run. A page investigated before reads only what is new since then. Pages
          in the people category run up to four at once, each with its own
          mailbox client. Other category runs start one page at a time.

For the model writing a page: the Skill covers the common case. Use supplied
material and, for projects, the supplied bounded repository snapshots. Unsupported
fields stay Unknown. Cite source IDs from evidence headings. Runs are offline;
the runner may offer one read-only mail follow-up outside a quick first pass.
Requires: co rem init.
Output:   The updated pages, and one line per page: accepted, refused (and why), or skipped.

Next:     co rem show PAGE
Back:     co rem --help
```

## co rem open

```
Open the notebook in your web browser to read it. Read-only: pages do not change.

Usage:    co rem open [--live] [--no-launch]
Example:  co rem open
          Renders a fresh snapshot of the notebook to a temporary file and opens
          it. Works offline; run it again to see newer pages.
          co rem open --live
          Opens the live view in O Chat, read from your co ai Host. Checks the
          Host first; if it is not online, says so (start it with co ai) and
          opens the snapshot instead. Only for the default notebook.
          --no-launch prints the page without opening a browser.
Effects:  Reads pages and changes none. The snapshot is written outside the
          notebook, to a temporary file.
Next:     co rem show PAGE   (to read one page in the terminal)
Back:     co rem --help
```

## co rem list

```
List pages in one category, or every category with its count. Read-only.

Usage:    co rem list [people|projects|orgs|skills|notes] [--aliases | --review]
Example:  co rem list people --aliases
          --aliases shows each person's addresses and other names.
          --review  shows the addresses held back: no name, and you never wrote
                    to them. A reply, a name, or investigating one brings it back.
Next:     co rem show PAGE
Back:     co rem --help
```

## co rem show

```
Print one page as Markdown. Read-only.

Usage:    co rem show PAGE
Example:  co rem show people/tamara-berryman-324b6af6e8.md
          co rem show me   (your own page)
Inputs:   PAGE comes from list, search, or the Next line of investigate.
Next:     co rem investigate PAGE   (if it still says Unknown)
Back:     co rem --help
```

## co rem search

```
Find text across pages, case-insensitive. Exact text, not meaning. No model.

Usage:    co rem search TEXT [--in people|projects|orgs|skills]
Example:  co rem search "term sheet" --in people
Next:     co rem show PAGE
Back:     co rem --help
```

## co rem start

```
Turn on daily upkeep. Shows exactly which sources will be read and which model will
run, asks you to approve, installs the schedule, and runs the first update. It asks
again whenever the sources, runner, model or schedule changed since you approved.
The first update runs on the first start only; a start after stop resumes the
schedule, and co rem sync runs an update now.

Usage:    co rem start [--yes]
Example:  co rem start
          --yes approves without the prompt. Use it only after you have read the summary once.

Effects:  Installs a launchd job (macOS) that runs `co rem sync --scheduled` at the
          times in co rem config (default 03:00 04:00 06:00 17:00 18:00 19:00 local).
          Each run reads new mail bodies and sessions and calls the model, at most
          `runner_calls_per_day` times a day. Nobody watches those runs, so the
          model is confined: Codex gets --sandbox workspace-write, Claude Code
          --permission-mode acceptEdits. It writes only under the notebook's
          .state/tasks, with no shell commands and no network.
Requires: co rem init. On Linux and Windows the schedule is not yet installed; run
          co rem sync yourself.

Next:     co rem status
Undo:     co rem stop
Back:     co rem --help
```

## co rem stop

```
Turn daily upkeep off by removing the schedule. Pages, source approvals and manual
co rem sync all stay.

Usage:    co rem stop
Example:  co rem stop
Next:     co rem status
Back:     co rem --help
```

## co rem status

```
Show whether the schedule is on, when it runs next, what ran today, and what it cost.
Read-only.

Usage:    co rem status [--verbose]
Example:  co rem status
Output:   One line each: the state and next run; the notebook (people, projects,
          organizations and skills, written of mapped, and what to write next);
          today's runs, pages changed and tokens; each mailbox with the command
          that fixes it; the last run.
Options:  --verbose   Also every internal field: schedule times, worker, token
                      counters and their coverage, the full last run record.
Next:     co rem logs   (details of each run)
Back:     co rem --help
```

## co rem sync

```
Run one update now: read what arrived since the last run and update the pages it
concerns. Then the day's first run investigates unfinished pages, most recent
first; every later run updates only the people and
projects with new mail or messages since the run before. This is what the
schedule runs.

Usage:    co rem sync [--dry-run] [--source NAME] [--with ADDRESS] [--all]
Example:  co rem sync --dry-run
          --dry-run   shows what is waiting, and the runner attempts left today and
                      when they reset, without reading bodies or calling a model
          --source    only one source from co rem sources
          --with      only mail with one person
          --all       keep going until nothing is waiting or the day's runner
                      attempts are spent; one line per batch on stderr. To go
                      further today, raise limits.runner_calls_per_day
          --scheduled what the schedule passes: run only if a scheduled time is due

Effects:  Reads message bodies, calls the model, updates pages. A run the daily
          cap refuses is kept in co rem logs. Ctrl-C keeps finished batches and
          says what finished; the interrupted one reads again next time.
Requires: co rem start (it records your approval of the sources).
Next:     co rem logs
Back:     co rem --help
```

## co rem sources

```
Show, add or remove what the notebook reads: gmail, outlook, codex, claude-code,
whatsapp. Showing is read-only.

Usage:    co rem sources
          co rem sources add NAME [--since 3d|2w|6m|1y] [--chat ID]... [--project DIR]
          co rem sources remove NAME [--chat ID]
Example:  co rem sources add whatsapp --chat 120363411567190840@g.us
          --chat      WhatsApp only: one chat to read. Ids come from co whatsapp chats.
                      No chat is read unless named.
          --since     how far back to read
          --project   coding sources: only sessions run in this directory

Effects:  add/remove change settings only. Bodies are read later, by sync, after start.
          remove stops future reads; pages already written stay.
Subcommands: co rem sources add --help, co rem sources remove --help
Next:     co rem sync --dry-run
Back:     co rem --help
```

## co rem config

```
Show or change settings. Changing validates every value before saving and never
starts a run on your mail or sessions.

Usage:    co rem config
          co rem config set KEY VALUE [KEY VALUE]... [--no-check]
Keys:     model                          gpt-6-luna (default); a new one is checked on a fixture page
          runner                         codex | claude-code | coai
          schedule.times                 "03:00,17:00"
          schedule.timezone              Australia/Sydney
          limits.runner_calls_per_day    6
          limits.timeout_seconds         600
          limits.<name>                  the other limits co rem config shows
          route.<stage>                  a model for one stage of planned investigation:
                                         plan, extract, synthesize or render ("default" clears it)
Example:  co rem config set model gpt-6-luna schedule.times "06:00,18:00"
Tier:     agent    the model drives tools: it reads the material and writes the page itself
          summary  a plain model: the material is handed over and it replies with the page
          Measured when model or runner changes, never read off the name. Unchecked runs
          as agent, and co rem config names the command that checks it.
Subcommand: co rem config set --help
Next:     co rem status
Back:     co rem --help
```

## co rem logs

```
What each run read, changed, refused and cost. Read-only.

Usage:    co rem logs [RUN] [--usage [--days N]]
Example:  co rem logs --usage --days 7
          RUN is an id from the listing and shows one run in full.
          --usage totals tokens by stage, model and source.
Next:     co rem logs RUN
Back:     co rem --help
```

## co rem doctor

```
Check that what the notebook needs is present: the co CLI, the model runner, mailbox
logins, session folders, spreadsheet support and the schedule. Read-only; it never
logs in or repairs.

Usage:    co rem doctor
Example:  co rem doctor
Output:   One line per check, with the command that fixes each failure.
Back:     co rem --help
```

## co rem config set

```
Change one or more settings. Every pair is checked before anything is saved: one
bad value saves nothing. Never starts a run on your mail or sessions.

Usage:    co rem config set KEY VALUE [KEY VALUE]... [--no-check]
Example:  co rem config set model gpt-6-luna limits.runner_calls_per_day 4
Keys:     the list on co rem config --help
          --no-check  save a new model or runner without checking its tier
Output:   The saved configuration, as co rem config prints it, and the tier.
Effects:  Writes config.yaml. A new schedule time takes effect at the next run.
          A new model or runner runs the capability check: one investigation of a
          built-in fixture page (two if tools fail), graded, then records the tier
          (agent or summary) in .state/tier.json. Calls the model; reads none of your data.
Next:     co rem config
Back:     co rem config --help
```

## co rem sources add

```
Start reading a source, or restore one you removed. Changes settings only: bodies
are read later by sync, after co rem start has recorded your approval.

Usage:    co rem sources add NAME [--since 3d|2w|6m|1y] [--only] [--force]
                                   [--chat ID]... [--project DIR] [--about TEXT]
          NAME is one of: gmail, outlook, codex, claude-code, whatsapp
Example:  co rem sources add codex --project ~/work/tide-agent --since 2w
          --chat     WhatsApp: one chat to read, from co whatsapp chats (repeatable).
                     No WhatsApp chat is read unless it is named here.
          --project  coding sources: only sessions run in this directory
          --about    coding sources: whole sessions that mention this text
          --since    read at least this far back; a wider window is left alone
          --only     with --since: read only that far back, narrowing the window
          --force    with --only: accept that unread older material is dropped
Next:     co rem sync --dry-run
Back:     co rem sources --help
```

## co rem sources remove

```
Stop reading a source from now on. Pages already written keep what they learned.

Usage:    co rem sources remove NAME [--chat ID]...
Example:  co rem sources remove whatsapp --chat 120363411567190840@g.us
          --chat   WhatsApp: stop only this chat, keep the others
Effects:  Writes settings. A removed mailbox is also skipped by investigate.
Next:     co rem sources
Back:     co rem sources --help
```

## co rem advanced

```
Commands for building and testing the notebook by hand, and experimental features.
Everyday use needs none of them.

Build by hand
  scan          List the people, organisations or projects a map would find. No pages written.
  map-skills    Map installed Skills only, without re-reading mail or sessions.
  stub          Create one empty page by hand, with every section marked Unknown.
Experimental: corrections and questions (#1611, #1609)
  reflect       Record a correction, a change, or a reflection about a page.
  reflections   Read the records for a page, or write a compact copy of them.
  propose       Save a question about a page, or a possible link between two pages.
  review        Answer the saved questions and links.
  abstract      Write decision and principle pages from the pages you already have.
Experimental: session capture (#1520)
  capture       Queue the user's messages from one coding-session file. Run by a hook.
Experimental: project pages from your own messages (#1943)
  projects      Write project pages from what you typed to Codex and Claude Code.

Back:     co rem --help
```

## co rem scan

```
List what a map would find, without writing pages. Useful to check a threshold
before init. Reads mail headers and session metadata. No model.

Usage:    co rem scan [people|orgs|projects] [--days N] [--min-mails N]
                       [--min-people N] [--mine ADDRESS]...
Example:  co rem scan people --days 30 --min-mails 5
          --min-mails   people: fewer messages than this is not listed (default 3)
          --min-people  orgs: a domain fewer people write from is not listed (default 2)
          --mine        an address that is yours, so it is not listed as someone else
Next:     co rem init
Back:     co rem advanced --help
```

## co rem map-skills

```
Map the installed Skills only: a catalog page for each, plus missing page frames.
Reads Skill files. Does not run them, does not read mail. No model.

Usage:    co rem map-skills [--skills-dir DIR]...
Example:  co rem map-skills --skills-dir ~/.claude/skills
          --skills-dir  read these folders instead of the defaults (repeatable)
Next:     co rem list skills
Back:     co rem advanced --help
```

## co rem stub

```
Create one page by hand, with its sections in place and every one marked Unknown,
for a subject the map did not find. Does nothing if the page exists. No model.

Usage:    co rem stub person|org|project NAME [--email ADDRESS] [--handle TEXT]...
                                                [--domain DOMAIN]... [--person PAGE]...
                                                [--path DIR]...
Example:  co rem stub person "Mei Lin" --email mei@harbourlabs.example
          --email   person: the address they are known by
          --handle  person: another spelling, address or alias (repeatable)
          --domain  org: a mail domain it owns (repeatable)
          --person  org: a person page that belongs to it (repeatable)
          --path    project: a folder it lives in (repeatable)
Next:     co rem investigate PAGE
Back:     co rem advanced --help
```

## co rem reflect

```
Record something the pages should take into account: a correction ("this is
wrong"), a change in the world ("she moved to Canva"), or a reflection. It is
kept as an attributed record, not written into the page. The next investigate
or sync of that page reads it as evidence, weighed against the rest; it is not
obeyed as an instruction.

Usage:    co rem reflect PAGE STATEMENT --author NAME --basis TEXT
                          [--kind reflection|correction|change] [--previous TEXT]
                          [--applies WHEN] [--source ID]... [--supersedes RECORD]...
Example:  co rem reflect people/mei-lin.md "Mei now leads partnerships" \
            --kind change --author "Sam" --basis "told me on a call" --applies 2026-09-20
          --author      who is asserting it (required)
          --basis       why it is believed (required)
          --previous    what the page said before, for a correction
          --applies     from when it is true
          --source      a source id that supports it (repeatable)
          --supersedes  an earlier record of this page that it replaces (repeatable)
Effects:  Writes one record under .state/reflections/. The page itself is unchanged.
Next:     co rem investigate PAGE
Back:     co rem advanced --help
```

## co rem reflections

```
Read the records kept for a page, or for every page. --compact writes a smaller
copy that loses nothing; the original records are never deleted. No model.

Usage:    co rem reflections [PAGE] [--compact]
Example:  co rem reflections people/mei-lin.md
Next:     co rem reflect PAGE STATEMENT --author NAME --basis TEXT
Back:     co rem advanced --help
```

## co rem propose

```
Save a question about one page, or a possible link between two pages, for a
person to answer with co rem review. Proposing the same thing twice keeps one.

Usage:    co rem propose question PAGE QUESTION --basis TEXT
          co rem propose link PAGE QUESTION --related PAGE --basis TEXT
Example:  co rem propose link people/mei-lin.md "Is Mei the Harbour Labs contact on this project?" \
            --related projects/tide-agent.md --basis "same week, same subject line"
          --basis    the evidence that raised it (required)
          --related  link only: the second page
Next:     co rem review
Back:     co rem advanced --help
```

## co rem review

```
List the saved questions and links, or answer one. A link takes yes or no; a
question takes an answer. A decided item is not asked again.

Usage:    co rem review
          co rem review ID --verdict yes|no --author NAME
          co rem review ID --verdict answer --author NAME (--response TEXT | --audio FILE --local-model FILE)
Example:  co rem review 3f2a91c0 --verdict answer --author "Sam" --response "Yes, since August"
          --audio        answer by voice: a recording, transcribed on this machine
          --local-model  the whisper.cpp model file for --audio; nothing is sent to the cloud
Effects:  Writes the decision. The next investigate of those pages reads it.
Next:     co rem review
Back:     co rem advanced --help
```

## co rem abstract

```
Write the layer above the pages: decision pages (a question that was settled,
with the alternative that was rejected), then principle pages (a reason that
keeps recurring across decisions). Reads pages only, never mail or sessions.
Runs the model once.

Usage:    co rem abstract
Example:  co rem abstract
Output:   Pages under decisions/ and principles/, cited to the pages they came from.
Effects:  Calls the model. Writes pages.
Next:     co rem list decisions
Back:     co rem advanced --help
```

## co rem capture

```
Queue the user's own messages from one Codex or Claude Code session file, so
they survive when the tool compacts or deletes the transcript. Normally run by a
hook, not by hand. Fast; no model, no sync.

Usage:    co rem capture FILE --source codex|claude-code
Example:  co rem capture ~/.claude/projects/-work-tide/3994b2ee.jsonl --source claude-code
Effects:  Appends to the notebook's capture queue. The next sync reads it.
Next:     co rem sync --dry-run
Back:     co rem advanced --help
```

## co rem projects

```
Write each project's page from your typed or explicitly transcribed voice input
to Codex and Claude Code in its folders, most recently active projects first. This shows what would be written
and what it would cost; it does not call a model.

It first files your new messages under their project pages (a script: only your input,
never assistant replies, mixed transcript deltas or tool output), in the notebook's private
.state/projects/, then lists the pages with messages they were not written from.
A message typed in a workspace holding several repositories (like ~/projects) is
filed under the repository its session worked in, judged from the paths its tool
calls touched; a session that touched none stays out. A folder with your messages
and no page gets a mapped page if it was active in the last N days; older ones
are listed, not created.

Usage:    co rem projects [--recent-days N] [--full]
Example:  co rem projects --recent-days 7
          --recent-days  projects active in the last N days come first, and folders
                         active in them get a page (default 14)
          --full         re-read the last 180 days instead of only what is new

Effects:  Writes .state/projects/ and new mapped pages under projects/. No model.
Output:   How many workspace messages were filed by repository, pages made, and
          folders left without one; then one line per page: last activity, new
          messages, first write or update; then the cost of writing them.
Subcommand: co rem projects write --help
Next:     co rem projects write
Back:     co rem advanced
```

## co rem projects write

```
Write the next project pages from your own messages, using a model: the pages
active in the last 14 days first, then older ones. A page written before gets only
the messages since; a page with nothing new is not written.

Usage:    co rem projects write [--limit N] [--recent-days N] [--full]
Example:  co rem projects write --limit 1
          --limit        at most N pages this run (default 5; 0 for all)
          --recent-days  projects active in the last N days come first (default 14)
          --full         re-read the last 180 days of sessions first

Effects:  States the cost, then one model call per page, one after another, with the
          runner in co rem config. A page replaces the old one only if every citation
          points at one of your messages; a refused page is kept with the reason and
          tried again next run. Counts toward investigation's weekly Codex budget.
Requires: co rem init.
Output:   One line per page: accepted, refused (and why) or failed; pages left.
Next:     co rem show PAGE
Back:     co rem projects --help
```
