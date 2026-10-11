# Release channels

ConnectOnion has two release channels:

- **Stable** is the default `pip install connectonion` channel for production.
- **Preview** contains opt-in alpha, beta, and release-candidate builds.

Preview releases never replace the stable recommendation. Install one by
pinning the exact version shown below. The pin alone lets pip take that one
preview. Do not add `--pre`: it applies to
every dependency too, and under it 1.8.8b7 resolved httpx 1.0.dev6, which has
no `AsyncClient`, and every remote agent call crashed.

## Current release

Stable **1.9.1** is the default production channel. co rem's first run now
investigates every page, deepens people with two years of mail, edits pages in
place and draws decisions and principles; Person pages lead with contact facts
and cited mail opens as a message. See [1.9.1 notes](releases/1.9.1.md) and the
[GitHub release](https://github.com/openonion/connectonion/releases/tag/v1.9.1).

```bash
python -m pip install --upgrade 'connectonion==1.9.1'
```

## Current preview

Beta **1.9.2b10**: a handoff mail you can read on a phone, whose paste-in block
installs co in its own environment and accepts in one go; one line installs
co; an accepted handoff makes each side the other's contact. See [1.9.2b10 notes](releases/1.9.2b10.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.2b10'
```

## Previous previews

Beta **1.9.2b9** adds `co mcp` (Experimental): call the connectors and MCP
servers you already have in Codex, such as Gmail, from the terminal, with no
second login and no model turn. See [1.9.2b9 notes](releases/1.9.2b9.md).

Beta **1.9.2b8**: a handoff now arrives as one prompt to paste into Codex or
Claude Code; the recipient's agent takes it from there, and questions come back
to the sender. See [1.9.2b8 notes](releases/1.9.2b8.md).

Beta **1.9.2b6** makes co rem's second pass go deeper: follow-up searches hand
back mail from people the notebook knows, and one editing turn rewrites the
lines the final round leaves saying what is not known. See
[1.9.2b6 notes](releases/1.9.2b6.md).

Beta **1.9.2b5** adds `co handoff` (Experimental): hand the work in a Codex or
Claude Code session to someone else's agent, which continues it in its own
session. Codex and Claude Code now learn co's commands at `co init`. See
[1.9.2b5 notes](releases/1.9.2b5.md).

Beta **1.9.2b4** hands a session's work to another person or their agent with
the `handoff` skill, and fixes what a real run of 1.9.2b3 found: REM reading
its own sessions, quoted Outlook searches, a background job macOS never
started, and installing on Intel Macs. See [1.9.2b4 notes](releases/1.9.2b4.md).

Beta **1.9.2b3** gives a first run you can read straight away: sources numbered
1, 2, 3, Company filled from the organisation page, probable duplicates named,
and people found by name. See [1.9.2b3 notes](releases/1.9.2b3.md).

Beta **1.9.2b2** was built and tested but not published; its changes are in
1.9.2b3. See [1.9.2b2 notes](releases/1.9.2b2.md).

Beta **1.9.2b1** lets each investigation pass delete as well as add, so pages
improve instead of only growing. See [1.9.2b1 notes](releases/1.9.2b1.md).

Release candidate **1.9.1rc1** waits long enough for its notebook and credential
locks when sixteen workers run at once. See [1.9.1rc1 notes](releases/1.9.1rc1.md).

Beta **1.9.1b5** scans coding sessions once per first run whatever window a page
asks for, and its mail backfill reads only mail. See [1.9.1b5 notes](releases/1.9.1b5.md).

Beta **1.9.1b4** scans your coding sessions once per first run instead of once
per person. See [1.9.1b4 notes](releases/1.9.1b4.md).

Beta **1.9.1b3** writes people's first pages without touching the network,
fetches attachments with the background backfill, and waits out a throttled
mailbox. See [1.9.1b3 notes](releases/1.9.1b3.md).

Beta **1.9.1b2** writes the first pages from mail already on disk, fetches each
person's older mail in the background and deepens those pages, and keeps
project pages that only had a citation wrong. See [1.9.1b2 notes](releases/1.9.1b2.md).

Beta **1.9.1b1** keeps a project page when only one citation is wrong, draws
decisions and principles from the first run, lists a page's documents, and runs
init 16 pages at a time. See [1.9.1b1 notes](releases/1.9.1b1.md).

Alpha **1.9.1a2** reads a large page's whole evidence in rounds, edits pages in
place with a lead-following investigation Skill, enriches organisations from
their own site, shows a person's contact facts first and opens a cited mail as
a message. See [1.9.1a2 notes](releases/1.9.1a2.md).

Alpha **1.9.1a1** maps the last 180 days on the first run and moves co rem's
generated maps and skill run reports from Notes to a Run logs category. See
[1.9.1a1 notes](releases/1.9.1a1.md).

Alpha **1.9.0a43** shows failed investigations on Home and explains the nightly
upkeep offer in init's overview. See [1.9.0a43 notes](releases/1.9.0a43.md).

Alpha **1.9.0a42** keeps completed People discovery after a later mail
connection failure and puts the historical contact directory before the mapped
People roster so a large first run does not bury it. See
[1.9.0a42 notes](releases/1.9.0a42.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a42'
co rem init --investigate-all --estimate-only
```

Alpha **1.9.0a41** adds a searchable directory of historical mail contacts,
an all-history first-run cost estimate, and the option to approve nightly REM
upkeep from `co rem init`. Gmail history uses bounded metadata requests. New
notebooks run on Claude Code with Sonnet 5.5 by default. See
[1.9.0a41 notes](releases/1.9.0a41.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a41'
co rem init --investigate-all --estimate-only
```

Alpha **1.9.0a40** distinguishes coding-session Skill name matches from
retained evaluation attempts and says explicitly that neither verifies the
installed version or task outcome. Mapped Skill pages put the investigation
command in the phone's first screen; Skill list links are easier to tap. See
[1.9.0a40 notes](releases/1.9.0a40.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a40'
co rem open --local
```

Alpha **1.9.0a39** puts direct 44-pixel source links beside a cited Skill
finding, so the specific original remains easy to open on a phone. Labelled
private findings hide those links when the reader hides private passages. See
[1.9.0a39 notes](releases/1.9.0a39.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a39'
co rem open --local
```

Alpha **1.9.0a38** adds a within-source find and Next match control to long
archived REM excerpts. It shows when an excerpt was truncated and searches only
the text shown; saved source bodies and memory pages do not change. See
[1.9.0a38 notes](releases/1.9.0a38.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a38'
co rem open --local
```

Alpha **1.9.0a37** shows a compact Project purpose on changed Home cards,
keeps the purpose's individual source links openable beside a clipped preview,
and enlarges the desktop privacy control. Saved memories do not change. See
[1.9.0a37 notes](releases/1.9.0a37.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a37'
co rem open --local
```

Alpha **1.9.0a36** keeps paragraph and table-field separators when Outlook
HTML mail becomes text. New REM source captures and `co outlook read` can show
event times, reasons and follow-up clauses separately. Already saved excerpts
are not rewritten. See [1.9.0a36 notes](releases/1.9.0a36.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a36'
co rem open --live
```

Alpha **1.9.0a35** puts the full-size source action beside the useful lead
on written REM pages. In a five-type 375×812 trial, each action fit within
the first viewport and still opened Sources. See
[1.9.0a35 notes](releases/1.9.0a35.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a35'
co rem open --live
```

Alpha **1.9.0a34** speeds scoped REM investigations by reusing a private
parsed window of typed coding-session inputs. On one 90-day notebook, a
source-only repeat in a new process fell from 103.5 to 2.1 seconds while
finding the same 4,957 messages. See
[1.9.0a34 notes](releases/1.9.0a34.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a34'
co rem open --live
```

Alpha **1.9.0a33** keeps Person first-contact facts and the People index tied
to evidence, updates first-run token and quota guidance from measured samples,
and shortens the release path without skipping its test gate. See
[1.9.0a33 notes](releases/1.9.0a33.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a33'
```

Alpha **1.9.0a32** keeps Skill pages tied to their invocation names, makes
cited run parts and local output files openable in the owner-only reader, and
labels intended outcomes separately from observed work. See
[1.9.0a32 notes](releases/1.9.0a32.md).

The a30 tag did not publish to PyPI after its release CI failed; see
[#2253](https://github.com/openonion/connectonion/issues/2253). Its full-cohort
changes are included in a31.

Earlier alpha previews remain available:

Alpha **1.9.0a31** checks Project claims against their adjacent originals
before replacing a page, supports deliberate retry, and includes the a30
full-cohort onboarding code. See [1.9.0a31 notes](releases/1.9.0a31.md).

Alpha **1.9.0a29** puts the mapped-page investigate action within phone reach
on the first screen. See [1.9.0a29 notes](releases/1.9.0a29.md).

Alpha **1.9.0a28** implements context over control in `co rem investigate`:
pre-authorizes local search and shell tools upfront, supplies live project
repository paths, and records full audit provenance. See
[1.9.0a28 notes](releases/1.9.0a28.md).

Alpha **1.9.0a27** keeps institutional and service desk senders out of the
People notebook and filters dated scratch tasks and prompt fragments from the
Projects notebook unless they have project evidence. See
[1.9.0a27 notes](releases/1.9.0a27.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a27'
co rem open --live
```

Earlier alpha previews remain available:

Alpha **1.9.0a26** reopens written `co rem` notebooks faster and makes it clear
when background updates are off while existing memories remain available. The
package README now checks its exact preview pin against the shipped version.
See [1.9.0a26 notes](releases/1.9.0a26.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a26'
co rem open --live
```

Alpha **1.9.0a25** shows what a first `co rem init` mapped, reconciles held
contacts, and corrects grouped mail dates on a fresh map. See
[1.9.0a25 notes](releases/1.9.0a25.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a25'
co rem open --live
```

Alpha **1.9.0a24** adds `co rem merge` to fold duplicate pages and preserve aliases.
See [1.9.0a24 notes](releases/1.9.0a24.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a24'
co rem open --live
```

Alpha **1.9.0a23** clarifies map-derived contact dates in the reader and keeps
table headers visible beside sticky columns on mobile. See
[1.9.0a23 notes](releases/1.9.0a23.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a23'
co rem open --live
```

Alpha **1.9.0a22** makes project findings and their evidence easier to check:
the current finding leads, partial session coverage is visible, and every
numbered source can be opened from the reader. See
[1.9.0a22 notes](releases/1.9.0a22.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a22'
co rem open --live
```

Alpha **1.9.0a21** shows the complete REM note and citations by default,
puts the note before Facts on phones, and gives investigation more weekly
room while retaining a 10% safety reserve. See
[1.9.0a21 notes](releases/1.9.0a21.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a21'
co rem open --live
```

Alpha **1.9.0a20** corrected visible **co rem** reader labels in the morning
overview, recall prompt, empty states and source dialogs. See
[1.9.0a20 notes](releases/1.9.0a20.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a20'
co rem open --live
```

Alpha **1.9.0a19** completes the public **co rem** rename: live reader links
use `/rem`, old `/wiki` addresses redirect, and the README, homepage and docs
share the same command name. See [1.9.0a19 notes](releases/1.9.0a19.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a19'
co rem init --days 5
```

Alpha **1.9.0a18**: REM's first-run owner page can lead with a cited change
of decision and its next step. The reader shows that change before the full
note and links cited project mentions; extracted fact citations survive the
quick-pass sample. The broader owner and REM maturity gates remain open.
See [1.9.0a18 notes](releases/1.9.0a18.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a18'
co rem init --days 5
```

Alpha **1.9.0a17**: REM's first written project page compares the owner's
requests with a bounded local README, package metadata and Git evidence.
Unsupported optional sections disappear after investigation, while supported
claims remain cited. Cross-page links and owner-page history are still open.
See [1.9.0a17 notes](releases/1.9.0a17.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a17'
co rem init --days 5
```

Alpha **1.9.0a16**: Gmail scans set a network timeout and avoid fetching
headers twice when a busy week must be split. A private 90-day first run
archived 3,202 messages and completed all 36 selected pages. See
[1.9.0a16 notes](releases/1.9.0a16.md).

Alpha **1.9.0a15**: REM's first run keeps its project list consistent with the
map it just showed. A later session scan prepares evidence for mapped projects
without silently adding project pages; unmatched folders remain private
candidates. This is a focused trust fix, with the broader overnight memory
review still open. See [1.9.0a15 notes](releases/1.9.0a15.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a15'
co rem init --days 5
```

Alpha **1.9.0a14**: `co rem init` now investigates the owner's page, recent
important people, active projects and related organizations by default. Its
roughly 20% weekly allowance target is advisory; selected work can finish
beyond it, subject to the configured safety floor. It also adds privacy labels
and a local reader toggle to the connected reader shipped in a13. See
[1.9.0a14 notes](releases/1.9.0a14.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a14'
co rem init
```

Alpha **1.9.0a13**: REM's local reader now leads each record with state,
actions, facts and connected context. The home is shorter and task-first;
source-backed field changes are separate from page rewrites. Archived citations
and cited conversations can be inspected in place when source bodies are
available. It remains a read-only preview with known limits. See
[1.9.0a13 notes](releases/1.9.0a13.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a13'
co rem open
```

<details>
<summary>The preview line that became 1.8.5</summary>

Beta **1.8.5b11** made the command line name what to run next, and made
calendar invitations actually arrive. `co gcalendar` never passed Google's
`sendUpdates`, so an event with attendees invited nobody — and `Event created`
read the same whether three people were invited or none, so the silent failure
was indistinguishable from success until a client's guest said they got nothing.
Moving or cancelling a meeting told its attendees nothing either, which is worse.
The confirmation now names who was invited, and echoes the time in the zone it
was written in: `16:30+10:00` used to be confirmed as `06:30 AM`.

An audit against `useful_skills/cli-skill-design` fixed four things in the CLI
itself. Every deliberate refusal printed two next steps, one of them useless and
read first by anyone merging streams. A typo ended at `co --help` even when
Click had already worked out the answer — `co larc` now says `Next: co lark`,
and `co like`, which nothing matches, says `Next: co commands` rather than
pointing at a boxed screen of groups. Two failures named no command at all. And
the `co env` skill had never learned about `rotate`, `--secret` or
`--from-console`.

A missing bot permission is now one link away instead of a Developer Console
visit, and #1462's reconnect gate passed: history recovery had never once been
allowed to run, and once it was, a message posted during a 90-second gap came
back exactly once.

It carries `b10`, which makes `co auth lark` create an application and return its
secret — **correcting b9, which shipped a warning saying it could not.** The
cause was one path segment. We printed the URL the SDK hands over,
`<open-host>/page/launcher?user_code=…`, and that page renders "Link expired"
whenever its own acknowledgement call fails, for a code the server reports as
pending in the same second. `lark-cli` discards that URL and builds
`<open-host>/page/cli?user_code=…`; pointed there, the same tenant produced the
creation form, an application, and its secret. Nothing about a tenant, a region,
or a code's lifetime was ever involved. `--app-id` reuse works too.

It carries `b9`, which lets an app secret be stored encrypted. `co env set --secret`
writes ciphertext under a key derived at a SLIP-0013 path and kept nowhere, and
`co env rotate` moves it to the next index. There is no master key, so there is
no keychain to be blocked by a sandbox or a machine with no logged-in human; the
root is `.co/keys/agent.key`, not the optional `recovery.txt`, so writing your
twelve words down and deleting that file cannot orphan a secret — and those
words still reach it, because the agent key is derived from them.

It also carries `co env set --from-console`, which accepts an app credential
copied from the Developer Console — still the right route when you already keep
an application there, though no longer the only way out of a tenant `co auth`
could not serve. And `co auth lark` reports the server's real link lifetime
instead of the SDK's fallback of 600, which is how "it expired after two
minutes" was investigated as a timeout that never existed.

It carries `b8`, which makes `co auth lark` begin on Lark. It used to print an
`open.feishu.cn` link and, on failure, tell a Lark user to run `co auth feishu`;
the accounts domain, the wording, and the reuse command offered from lark-cli's
config all follow the brand now.

It carries `b7`, which lets an agent reach a tab the site opened for itself — a
payment popup, a "view invoice" button, any `target="_blank"` link. Those pages
belong to no session, so they appeared on no board and every `-t` command kept
running in the page before them. `co browser list_pages` shows the browser's
real pages with the session driving each, `switch_page <index>` points a session
at one, and `tab ls` counts what it cannot show and names the verb.

It carries `b6`, which installs the paid browser's driver from PyPI. `onionwright`
held only a name reservation there — one file and a version string — while the
real client travelled a licence-gated endpoint; it is published normally now, so
`pip install 'connectonion[wtf]'` works and the installer is 289 lines shorter.
The browser binary stays licence-gated and the runtime licence is still checked
at launch.

It carries `b5`, which makes asking for the paid engine enough. The route to the WTF
Browser was three commands, and the first one asked the caller to decide nothing —
the engine cannot run without its client. An explicit `--engine wtf` now fetches
it; `auto`, `system` and `--engine wtf help` still install nothing, because
importing ConnectOnion or taking the free engine must never mutate a Python
environment. The paid browser also runs on **Intel Macs** now: its object had
been staged and unpromoted since a gate failure on 2026-09-04, and the re-run
passed on real Intel hardware on 2026-09-13.

It carries `b4`, which fixes what `b3` could not install. `co browser install-onion`
reported `pip could not install Onionwright (exit 1)` when pip had declined by
policy — PEP 668's externally-managed marker, the default on Homebrew and most
distro Pythons — and had named the override itself. pip's output is captured now
so a refusal can be told from a failure, and a policy refusal names the
interpreter and both routes out. The new `--break-system-packages` is opt-in.

It carries everything from `b3`, which fixes two ways the browser could waste an afternoon, both
found by an unattended agent. `co browser wait` takes seconds while every
neighbouring knob is named in milliseconds, so `wait 2500` meant forty-one
minutes holding a tab's lock — every command behind it timed out while
`status` kept answering, so nothing looked broken. It is capped at 60 seconds
now and refuses before taking the lock, naming the value you meant. And a
daemon pinned to an engine refused every bare command, `close` included, while
its own error told you to run `close`: `auto` is no preference now, verbs that
touch no page are never gated, and a refusal names only commands that daemon
would accept. A dead paid session names its recovery, and the paid engine says
it bills before it spends.

It carries everything from `b2`: `co browser config`, the paid engine called
`wtf`, `consume`, and `co auth feishu --app-id`.

The no-loss-across-a-reconnect gate passed on 15 September, against a real
group — the last thing between this line and stable.
See [1.8.5b11 release notes](releases/1.8.5b11.md).

</details>

All eleven 1.8.5 previews (a1 through b11) are superseded by stable 1.8.5;
1.8.4a1 and 1.8.4a2
are historical, and the planned 1.8.4b1 was folded into the stable release. The
tag workflow builds and verifies the public package before documentation is
deployed. Google authorization from 1.8.3 is retained; TikTok remains deferred.
The sections below are historical notes.

## Historical 1.7 preview work

- Stable release: `1.6.10`
- Preview target: `1.7.0a13`
- Browser client: `@connectonion/react@0.4.2-alpha.11`

The preview uses OIP 0.1 as the only first-party browser protocol. The Python
Host serves the authenticated `/ws` connection; `@connectonion/react` owns the
browser client; O Chat consumes the exact React prerelease. Codex and Claude
Code remain native backend provider adapters and publish their normalized
activity through OIP.

Alpha 7 makes explicit Codex requests deterministic: natural-language verbs,
`/codex`, delegation language, and Chinese requests route through the native
Codex adapter before the model chooses a tool. `open Codex` creates or resumes
the provider session without inventing a prompt, and an OIP-visible guard blocks
direct Codex launches through shell tools without affecting ordinary shell text.
The browser continues to use OIP 0.1 and the same shared Work Room card.

Alpha 8 closes the open-only lifecycle found by public browser acceptance.
Codex writes a rollout only after its first turn, so an open-only app-server now
stays alive in a bounded, expiring registry. The first Work Room message claims
that exact provider thread, completes the real turn, persists the rollout, and
then closes the process. The session ID shown when Codex opens is therefore the
same one used by the first task.

Alpha 9 makes reload an authenticated OIP reattach instead of a false second
login. A fresh signed CONNECT that reaches the still-live relay queue is accepted
only when caller, recipient, signed-command capability, OIP protocol, and session
are unchanged. The Host republishes CONNECTED without duplicating a running
forwarder; every mismatch and signature replay remains rejected.

Alpha 10 separates that reattach proof from first-connect authorization. The
same live caller must still present a fresh signature and unchanged recipient,
capability, protocol, session, replay claim, and current blacklist status, but
the Host no longer repeats mutable onboarding/contact/admin policy or rebuilds
permission authority for a connection that is already authorized. It republishes
the existing mode, profile, transcript, and dashboard state. A first Send or
Codex Work Room follow-up racing the eager browser CONNECT now reaches its input
instead of surfacing a local trust-file error.

Alpha 11 makes the OIP 0.1 rolling window explicit. Descriptor-less 0.1 peers
remain readable, Direct and Relay use the same compatibility gate, unsupported
versions fail once without retry, discovery stays uncached, and Host records only
content-free compatibility classifications. DD-053 now defines the release and
time boundary before a reader can be removed.

Alpha 12 closes the production blockers found by real Chrome acceptance. Claude
Code keeps its authenticated macOS CLI environment and publishes a resumable
Work Room lifecycle like Codex. Stop now terminates the complete hosted Bash
process group, and multimodal messages no longer crash slash-command dispatch or
lose their image parts. The release gate includes fresh onboarding, approval,
cancellation with a process-tree check, text and image attachments, reconnect,
both native coding adapters, mobile layout, and session rollback across exact
published React and Host prereleases.

Alpha 13 makes a long native coding run observable while it is still running.
Codex and Claude Code emit their provider lifecycle and child work in a live,
non-persistent presentation lane; their canonical trace remains transactional
until the outer hosted tool commits. A cancellation closes the live provider
card without leaking that uncommitted trace. Native Codex approvals now carry
safe exact provider correlation, so React and O Chat put the decision on the
right Work Room card instead of a generic outer tool. The default UI presents a
bounded semantic activity snapshot; raw commands and outputs stay behind
disclosure.

Normal upgrades stay on stable. Preview testers opt in explicitly:

```bash
python -m pip install connectonion==1.7.0a13
```

## Design Journal

Release notes record what changed. A Design Journal post records the problem,
alternatives, decision, tradeoffs, evidence, and what would make us revisit it.
Meaningful feature-train launches, phase promotions, stable releases, and
material architecture decisions receive a new or substantially updated post.

The OIP-only decision is recorded in
[DD-053](design-decisions/053-oip-only-browser-and-native-coding-adapters.md).
