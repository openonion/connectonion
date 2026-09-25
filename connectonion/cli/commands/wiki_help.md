# co wiki help pages

Each section is printed verbatim by `--help` for the command it names.
The agreed design is issue #1656; change a page there and here together.

## co wiki

```
co wiki — a notebook about the people, projects and tools in your work, kept up to date from your mail and coding sessions.

Build (once)
  init          Build the notebook's frame from mail headers and coding sessions. No model.
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
  --root DIR    The notebook folder (default ~/.co/wiki).
  --json        Machine-readable output: {"ok", "data", "next"}.

First time:   co wiki init
Every page:   co wiki <command> --help
Advanced:     co wiki advanced --help   (scan, map-skills, stub, reflect, reflections,
              propose, review, abstract, capture)
Old names:    unfinished, people, daily, subscriptions, subscribe, unsubscribe, route
              and usage still work until 1.9 and print their new name.
```

## co wiki init

```
Build the notebook's frame: a page for each person you write to, each organization,
each coding project and each installed Skill, plus your own page, already titled
with your name and filled with who you write to most and where you work. Reads mail headers
and session metadata only. Does not read message bodies, does not run a model, does
not turn on the schedule.

Usage:    co wiki init [--days N] [--mine ADDRESS]... [--name NAME] [--mail gmail|outlook]...
Example:  co wiki init --days 90 --name "Aaron Xie" --mine aaron@mail.openonion.ai

Inputs:   Connected mailboxes (co auth google, co auth microsoft) and local Codex /
          Claude Code sessions. --mine adds an address that is yours; init also lists
          addresses that look like yours and prints the --mine command for each.
Output:   Pages under ~/.co/wiki (or --root). A summary of what was read, what was
          skipped and why, and the pages created. Re-running keeps anything written.
Effects:  Writes pages. Reads mail headers. No model, no cost, no schedule.
Takes:    About 10 minutes for 90 days of two mailboxes.

Next:     co wiki investigate me         (fill your own page first)
Back:     co wiki --help
```

## co wiki investigate

```
co wiki investigate — fill pages from everything about their subject, using a model.

A page is filled only from what it was given. The new page replaces the old one
only if every citation points at a message, file or URL the run supplied. A
refused page is kept, with the reason, so the model's work is never lost.

Usage:
  co wiki investigate                          List what is left to investigate, by category. No model.
  co wiki investigate PAGE                     Investigate one page.
  co wiki investigate CATEGORY [--limit N]     Investigate the unfinished pages in one category,
                                               most useful first. Default --limit 5.
  co wiki investigate me                       Investigate your own page from your recent work.

  CATEGORY is one of: people, projects, orgs, skills

Examples:
  co wiki investigate
  co wiki investigate people/ody-zhou-c6a901ffd8.md
  co wiki investigate people --limit 3
  co wiki investigate projects --list          (show the order, run nothing)

What each kind reads:
  people    Every message to or from their addresses, searched on the server, with
            readable attachments; coding sessions that mention them.
  projects  The coding sessions run in the project's folders, and the project's own files.
  orgs      Mail from the organisation's domains, and the people pages under it.
  skills    Recorded runs of the Skill (co eval results; --eval-dir to choose where).
  me        Your own sent mail and coding sessions from the last --days (default 30).

Options:
  --days N       How far back to read (default 150; 30 for me)
  --limit N      With CATEGORY: at most N pages this run (default 5; 0 for all)
  --list         With CATEGORY: print the order and stop; no model
  --handle TEXT  PAGE only: another address or name for the subject (repeatable)
  --eval-dir DIR skills only: where the run records are

Order within a category: pages still marked Unknown first, then those with the
most mail or sessions. A page investigated in the last 7 days is skipped.

Effects:  Reads message bodies and files. Calls the model configured in co wiki config:
          one call for most pages. A subject with hundreds of messages is summarised
          in parts first, and can take 30–40 minutes. Pages run one after another,
          not in parallel. The mailbox servers throttle parallel reads.
Requires: co wiki init.
Output:   The updated pages, and one line per page: accepted, refused (and why), or skipped.

Next:     co wiki show PAGE
Back:     co wiki --help
```

## co wiki open

```
Open the notebook in your browser, as a private page on your own agent.
Read-only.

Usage:    co wiki open [--local] [--no-launch]
Example:  co wiki open
          --local opens a static snapshot file instead of the live page.
Effects:  None to pages.
Next:     co wiki show PAGE   (to read one page in the terminal)
Back:     co wiki --help
```

## co wiki list

```
List pages in one category, or every category with its count. Read-only.

Usage:    co wiki list [people|projects|orgs|skills|notes] [--aliases]
Example:  co wiki list people --aliases
          --aliases shows each person's addresses and other names.
Next:     co wiki show PAGE
Back:     co wiki --help
```

## co wiki show

```
Print one page as Markdown. Read-only.

Usage:    co wiki show PAGE
Example:  co wiki show people/tamara-berryman-324b6af6e8.md
Inputs:   PAGE comes from list, search, or the Next line of investigate.
Next:     co wiki investigate PAGE   (if it still says Unknown)
Back:     co wiki --help
```

## co wiki search

```
Find text across pages, case-insensitive. Exact text, not meaning. No model.

Usage:    co wiki search TEXT [--in people|projects|orgs|skills]
Example:  co wiki search "term sheet" --in people
Next:     co wiki show PAGE
Back:     co wiki --help
```

## co wiki start

```
Turn on daily upkeep. Shows exactly which sources will be read and which model will
run, asks you to approve once, installs the schedule, and runs the first update.

Usage:    co wiki start [--yes]
Example:  co wiki start
          --yes approves without the prompt. Use it only after you have read the summary once.

Effects:  Installs a launchd job (macOS) that runs `co wiki sync --scheduled` at the
          times in co wiki config (default 03:00 04:00 06:00 17:00 18:00 19:00 local).
          Each run reads new mail bodies and sessions and calls the model, at most
          `runner_calls_per_day` times a day. Nobody watches those runs, so the
          model is confined: Codex gets --sandbox workspace-write, Claude Code
          --permission-mode acceptEdits. It writes only under the notebook's
          .state/tasks, with no shell commands and no network.
Requires: co wiki init. On Linux and Windows the schedule is not yet installed; run
          co wiki sync yourself.

Next:     co wiki status
Undo:     co wiki stop
Back:     co wiki --help
```

## co wiki stop

```
Turn daily upkeep off by removing the schedule. Pages, source approvals and manual
co wiki sync all stay.

Usage:    co wiki stop
Next:     co wiki status
Back:     co wiki --help
```

## co wiki status

```
Show whether the schedule is on, when it runs next, what ran today, and what it cost.
Read-only.

Usage:    co wiki status
Next:     co wiki logs   (details of each run)
Back:     co wiki --help
```

## co wiki sync

```
Run one update now: read what arrived since the last run, update the pages it
concerns, then investigate at most one unfinished page. This is what the schedule
runs.

Usage:    co wiki sync [--dry-run] [--source NAME] [--with ADDRESS] [--all]
Example:  co wiki sync --dry-run
          --dry-run   shows what is waiting without reading bodies or calling a model
          --source    only one source from co wiki sources
          --with      only mail with one person
          --all       keep going until nothing is waiting (ignores the daily cap)
          --scheduled what the schedule passes: run only if a scheduled time is due

Effects:  Reads message bodies, calls the model, updates pages.
Requires: co wiki start (it records your approval of the sources).
Next:     co wiki logs
Back:     co wiki --help
```

## co wiki sources

```
Show, add or remove what the notebook reads: gmail, outlook, codex, claude-code,
whatsapp. Showing is read-only.

Usage:    co wiki sources
          co wiki sources add NAME [--since 3d|2w|6m|1y] [--chat ID]... [--project DIR]
          co wiki sources remove NAME [--chat ID]
Example:  co wiki sources add whatsapp --chat 120363411567190840@g.us
          --chat      WhatsApp only: one chat to read. Ids come from co whatsapp chats.
                      No chat is read unless named.
          --since     how far back to read
          --project   coding sources: only sessions run in this directory

Effects:  add/remove change settings only. Bodies are read later, by sync, after start.
          remove stops future reads; pages already written stay.
Subcommands: co wiki sources add --help, co wiki sources remove --help
Next:     co wiki sync --dry-run
Back:     co wiki --help
```

## co wiki config

```
Show or change settings. Changing validates every value before saving and never
starts a run.

Usage:    co wiki config
          co wiki config set KEY VALUE [KEY VALUE]...
Keys:     model                          gpt-6-luna (default: the newest generation's cheapest)
          runner                         codex | claude-code | coai
          schedule.times                 "03:00,17:00"
          schedule.timezone              Australia/Sydney
          limits.runner_calls_per_day    6
          limits.timeout_seconds         600
          limits.<name>                  the other limits co wiki config shows
          route.<stage>                  a model for one stage of planned investigation:
                                         plan, extract, synthesize or render ("default" clears it)
Example:  co wiki config set model gpt-6-luna schedule.times "06:00,18:00"
Subcommand: co wiki config set --help
Next:     co wiki status
Back:     co wiki --help
```

## co wiki logs

```
What each run read, changed, refused and cost. Read-only.

Usage:    co wiki logs [RUN] [--usage [--days N]]
Example:  co wiki logs --usage --days 7
          RUN is an id from the listing and shows one run in full.
          --usage totals tokens by stage, model and source.
Next:     co wiki logs RUN
Back:     co wiki --help
```

## co wiki doctor

```
Check that what the notebook needs is present: the co CLI, the model runner, mailbox
logins, session folders and the schedule. Read-only; it never logs in or repairs.

Usage:    co wiki doctor
Output:   One line per check, with the command that fixes each failure.
Back:     co wiki --help
```

## co wiki config set

```
Change one or more settings. Every pair is checked before anything is saved: one
bad value saves nothing. Never starts a run.

Usage:    co wiki config set KEY VALUE [KEY VALUE]...
Example:  co wiki config set model gpt-6-luna limits.runner_calls_per_day 4
Keys:     the list on co wiki config --help
Output:   The saved configuration, as co wiki config prints it.
Effects:  Writes config.yaml. A new schedule time takes effect at the next run.
Next:     co wiki config
Back:     co wiki config --help
```

## co wiki sources add

```
Start reading a source, or restore one you removed. Changes settings only: bodies
are read later by sync, after co wiki start has recorded your approval.

Usage:    co wiki sources add NAME [--since 3d|2w|6m|1y] [--only] [--force]
                                   [--chat ID]... [--project DIR] [--about TEXT]
          NAME is one of: gmail, outlook, codex, claude-code, whatsapp
Example:  co wiki sources add codex --project ~/work/tide-agent --since 2w
          --chat     WhatsApp: one chat to read, from co whatsapp chats (repeatable).
                     No WhatsApp chat is read unless it is named here.
          --project  coding sources: only sessions run in this directory
          --about    coding sources: whole sessions that mention this text
          --since    read at least this far back; a wider window is left alone
          --only     with --since: read only that far back, narrowing the window
          --force    with --only: accept that unread older material is dropped
Next:     co wiki sync --dry-run
Back:     co wiki sources --help
```

## co wiki sources remove

```
Stop reading a source from now on. Pages already written keep what they learned.

Usage:    co wiki sources remove NAME [--chat ID]...
Example:  co wiki sources remove whatsapp --chat 120363411567190840@g.us
          --chat   WhatsApp: stop only this chat, keep the others
Effects:  Writes settings. A removed mailbox is also skipped by investigate.
Next:     co wiki sources
Back:     co wiki sources --help
```

## co wiki advanced

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

Back:     co wiki --help
```

## co wiki scan

```
List what a map would find, without writing pages. Useful to check a threshold
before init. Reads mail headers and session metadata. No model.

Usage:    co wiki scan [people|orgs|projects] [--days N] [--min-mails N]
                       [--min-people N] [--mine ADDRESS]...
Example:  co wiki scan people --days 30 --min-mails 5
          --min-mails   people: fewer messages than this is not listed (default 3)
          --min-people  orgs: a domain fewer people write from is not listed (default 2)
          --mine        an address that is yours, so it is not listed as someone else
Next:     co wiki init
Back:     co wiki advanced --help
```

## co wiki map-skills

```
Map the installed Skills only: a catalog page for each, plus missing page frames.
Reads Skill files. Does not run them, does not read mail. No model.

Usage:    co wiki map-skills [--skills-dir DIR]...
Example:  co wiki map-skills --skills-dir ~/.claude/skills
          --skills-dir  read these folders instead of the defaults (repeatable)
Next:     co wiki list skills
Back:     co wiki advanced --help
```

## co wiki stub

```
Create one page by hand, with its sections in place and every one marked Unknown,
for a subject the map did not find. Does nothing if the page exists. No model.

Usage:    co wiki stub person|org|project NAME [--email ADDRESS] [--handle TEXT]...
                                                [--domain DOMAIN]... [--person PAGE]...
                                                [--path DIR]...
Example:  co wiki stub person "Mei Lin" --email mei@harbourlabs.example
          --email   person: the address they are known by
          --handle  person: another spelling, address or alias (repeatable)
          --domain  org: a mail domain it owns (repeatable)
          --person  org: a person page that belongs to it (repeatable)
          --path    project: a folder it lives in (repeatable)
Next:     co wiki investigate PAGE
Back:     co wiki advanced --help
```

## co wiki reflect

```
Record something the pages should take into account: a correction ("this is
wrong"), a change in the world ("she moved to Canva"), or a reflection. It is
kept as an attributed record, not written into the page. The next investigate
or sync of that page reads it as evidence, weighed against the rest; it is not
obeyed as an instruction.

Usage:    co wiki reflect PAGE STATEMENT --author NAME --basis TEXT
                          [--kind reflection|correction|change] [--previous TEXT]
                          [--applies WHEN] [--source ID]... [--supersedes RECORD]...
Example:  co wiki reflect people/mei-lin.md "Mei now leads partnerships" \
            --kind change --author "Sam" --basis "told me on a call" --applies 2026-09-20
          --author      who is asserting it (required)
          --basis       why it is believed (required)
          --previous    what the page said before, for a correction
          --applies     from when it is true
          --source      a source id that supports it (repeatable)
          --supersedes  an earlier record of this page that it replaces (repeatable)
Effects:  Writes one record under .state/reflections/. The page itself is unchanged.
Next:     co wiki investigate PAGE
Back:     co wiki advanced --help
```

## co wiki reflections

```
Read the records kept for a page, or for every page. --compact writes a smaller
copy that loses nothing; the original records are never deleted. No model.

Usage:    co wiki reflections [PAGE] [--compact]
Example:  co wiki reflections people/mei-lin.md
Next:     co wiki reflect PAGE STATEMENT --author NAME --basis TEXT
Back:     co wiki advanced --help
```

## co wiki propose

```
Save a question about one page, or a possible link between two pages, for a
person to answer with co wiki review. Proposing the same thing twice keeps one.

Usage:    co wiki propose question PAGE QUESTION --basis TEXT
          co wiki propose link PAGE QUESTION --related PAGE --basis TEXT
Example:  co wiki propose link people/mei-lin.md "Is Mei the Harbour Labs contact on this project?" \
            --related projects/tide-agent.md --basis "same week, same subject line"
          --basis    the evidence that raised it (required)
          --related  link only: the second page
Next:     co wiki review
Back:     co wiki advanced --help
```

## co wiki review

```
List the saved questions and links, or answer one. A link takes yes or no; a
question takes an answer. A decided item is not asked again.

Usage:    co wiki review
          co wiki review ID --verdict yes|no --author NAME
          co wiki review ID --verdict answer --author NAME (--response TEXT | --audio FILE --local-model FILE)
Example:  co wiki review 3f2a91c0 --verdict answer --author "Sam" --response "Yes, since August"
          --audio        answer by voice: a recording, transcribed on this machine
          --local-model  the whisper.cpp model file for --audio; nothing is sent to the cloud
Effects:  Writes the decision. The next investigate of those pages reads it.
Next:     co wiki review
Back:     co wiki advanced --help
```

## co wiki abstract

```
Write the layer above the pages: decision pages (a question that was settled,
with the alternative that was rejected), then principle pages (a reason that
keeps recurring across decisions). Reads pages only, never mail or sessions.
Runs the model once.

Usage:    co wiki abstract
Example:  co wiki abstract
Output:   Pages under decisions/ and principles/, cited to the pages they came from.
Effects:  Calls the model. Writes pages.
Next:     co wiki list decisions
Back:     co wiki advanced --help
```

## co wiki capture

```
Queue the user's own messages from one Codex or Claude Code session file, so
they survive when the tool compacts or deletes the transcript. Normally run by a
hook, not by hand. Fast; no model, no sync.

Usage:    co wiki capture FILE --source codex|claude-code
Example:  co wiki capture ~/.claude/projects/-work-tide/3994b2ee.jsonl --source claude-code
Effects:  Appends to the notebook's capture queue. The next sync reads it.
Next:     co wiki sync --dry-run
Back:     co wiki advanced --help
```
