# Why `rem-investigate` says what it says

The runtime Skill `connectonion/useful_skills/rem-investigate/SKILL.md` holds
only the rules, because it is re-sent on every model turn and every Codex tool
round of a co rem investigation (#1851). This file holds the reasons, incidents and
examples behind those rules. It is not loaded at runtime. When you change a rule
there, update its reason here in the same change.

## Group replies after a recipient is dropped

A real person page still said the client owed scope approval, while another
page recorded that client's approval and the team's later wording changes.
The first person was copied on the request but absent from later replies.
Address-only archive selection kept the request and missed its resolution.

Person archive material now also includes saved messages with the same exact
provider/thread identifier as direct indexed messages. There is no subject-line
matching or transitive expansion. Missing identifiers or unsaved bodies supply
no additional context. These messages carry a relationship-scope warning and
are excluded from extracted personal contact facts. They do not prove the
person wrote the reply, received it or owns the group's task.

Indexed evidence now includes raw participant metadata, including Cc; a
provider-rendered body may omit it. The writer must distinguish the requester,
decision maker and debtor, and match the team and actual ask before closing it.
A shared install/poll thread can contain replies from different teams.

The inspected person's material grew from six direct messages to twelve:
three later approval/wording replies and three replies on shared threads.
Only the matching scope replies resolve the original approval. A second page's
reversed approval obligation was manually corrected: a co-recipient is not
automatically assigned the client's work. These manual changes do not establish
automatic compliance. The full notebook's index adds 96 context/page pairs to
17 of 36 person pages; these are overlapping evidence, not 96 verified findings.

The focused gate also caught instruction-budget failures. Person rules and
session-workspace wording were compacted without raising the 15,000 limit;
all current instruction-composition checks pass. Exact rendered/source coverage
and remaining gaps are recorded in the round's review report.

## Organization context across mail domains (#2157)

Domain-only investigation split a real offer/acceptance timeline across two
organization pages. A shared canonical contact now supplies exact candidate
addresses on the other mapped domain pages. Primary dated mail is gathered from
those addresses, including Cc, while other correspondents on the other domain
remain outside the comparison. This does not merge organizations or establish
identity: the map can group people by display name, so the model must verify the
person/company from the messages and preserve uncertain domain ownership.
The mapped target domains keep their scope when a generated page lists a
possible alias; that generated note cannot authorize reading the alias's whole
domain as the same organization. Unmapped pages use their declared Domains.

Outside-domain correspondence and its attachments carry an explicit relationship
scope in inline and searchable evidence. Previously cited primary messages are
retained when new related-contact evidence needs comparison. Domain-only and
candidate contact dates are not forced into entity-level Facts during that
comparison; the model must establish the entity scope from the cited messages.
An accepted credits/startup-tier offer does not prove acceptance of a separate
free-month offer, activation or completed setup. A later unrelated exchange
does not close an older unanswered request.

Before the split (2026-09-30) the Skill was 23.7k characters and investigate for
one person page composed to ~31k; the rules-only version is ~9.5k.

## Input: the page as it stands, fully read first

- The page already exists with every section in place, uninvestigated ones
  marked `Unknown`. The structure is settled; the run fills it and keeps it
  current rather than writing from scratch.
- **Read what you were given before looking anywhere else.** On evaluation runs
  the turns went on searching the workspace for another page to copy, and the
  page was never written.
- The four-way table (Unknown / agrees / moved on / contradicts) exists because
  each case needs a different treatment; rewording a correct value creates diff
  noise, and silently picking between contradictory values hides the question.
- **An `Unknown` you searched for stays `Unknown` with one line in
  `Uncertainties`.** That sentence stops the next run from spending another pass
  on the same dead end, and it is the difference between "we do not know" and
  "nobody has looked".
- **Thin material, said so.** The stage this replaces produced 143 pages with a
  median of 700 bytes, twenty of them a single line, because it met each person
  a few messages at a time and wrote what each batch happened to know. An
  investigation sees all material at once, so a thin section means thin
  material, and the reader should be told rather than left to guess.

## What `Uncertainties` is for

It is read by the user deciding what to trust. Five kinds of line kept
appearing on real pages on 2026-09-23 and none told the user anything about the
person:

| Do not write | Why |
|---|---|
| "Gmail was searched over 150 days with 0 matches; Codex had 423 messages, 0 related." | Coverage. It goes in the final reply. |
| "The existing page recorded 37 mails; the material has 52." | The map's counts come from a shorter window. They are placeholders. |
| "No organisation page exists for UNSW in the notebook." | About the notebook, not the person. |
| "No other address or second page for Misa was found." | A search that found nothing about identity is not news. Name a duplicate only when you see one. |
| "No attachments were read." | Coverage again. |

Lines worth keeping: "Role: not in her signature or on fis.com; unknown." --
"Whether the 2026-09-22 meeting happened is not in the mail." -- "Signed as
‘Ody’ and as ‘欧弟’; assumed the same person from the shared address."

**No citation on `Unknown`.** `How the user writes to them: Unknown — no message
from the user [8]` and `Phone: Unknown [W1]` cite a source for something it does
not contain. The search belongs in `Uncertainties`.

## Identity is given, not guessed

- **The user's own addresses.** Every message in the material was sent to or
  from the user, so the user's addresses sit beside the subject's on every row.
  Without the rule they leaked into subjects' `Email` fields.
- The subject arrives with its handles already resolved (names, spellings,
  addresses, paths) — you do not have to work out who "odi" is. So the ordinary
  maintenance rule (search first, judge carefully, mark a possible twin) does
  not apply the same way here.
- **Every given handle on the page, wrong spellings too:** that line is how the
  daily pass recognises the subject without thinking. Discovered handles let the
  next sweep reach material this one could not.
- **A handle that produced nothing is a finding** (unless it is the page's own
  address) because it tells the next run the handle is dead.
- **Title from the name.** The map created `# vern.chan` from an address; a
  signature reading "Vern Chan" makes the title `# Vern Chan`. The title is what
  the user will search for.
- **Self-profile.** When the subject is a mailbox owner, a notice addressed to
  them (e.g. from a vendor) was being read as their own role or company, and a
  "relationship between the user and themself" was invented.
- **Duplicates are named, not merged**, because merging needs a human decision.

## Read across sources before writing

The point of the stage is that sources correct each other; writing from the
first source and patching with the rest loses that.

- **Signature block.** The one place people write down who they are, and it is
  already in the material. `Role: UNSW Global Program Manager` and `Company: UNSW
  Founders + Office of Global Affairs, L1 Hilmer Building, Kensington` came out
  of four lines under "Thank you," and cost nothing.
- **Domain as employer.** 168 of 182 real correspondents over 180 days wrote
  from a work domain, so this is the most reliable free fact in the mailbox. It
  is taken at the source stage, not from the web and not only when a field is
  `Unknown`. It does not say which part of the organisation (the signature
  does) and never a title. A mailbox provider names no employer — pages had
  "Company: Gmail".
- **Org pages.** Institutional detail lives on the org page so it is written
  once; two people from one domain with no page is what `co rem scan orgs` /
  `co rem stub org` are for.
- **Attachments are where the terms are.** The mail says "please see
  attached"; the attachment says 7.5% of Net Booking Revenue. An unreadable file
  is a known gap, not an absence.
- **Coding sessions** carry intent — why the user was doing it, what they were
  weighing — but almost never a full name; a first name or whatever dictation heard.
- **Disagreement is the interesting part** (a name spelled two ways, a count
  that changed, a renegotiated term). A fact one source states and another
  implies is stronger than either, hence citing both.

## What to produce

- The person template's headings and `Contact` labels are read back by the
  roster behind `co rem list people --aliases`; a renamed section is invisible
  and the next batch meets the person as a stranger again.
- **`Open threads` mandatory.** From a real investigation: "the contract is still
  in draft, the listings are already co-hosted, and reported income is A$0
  because the agreement is unsigned" was all on the page, spread across three
  other sections, so it read as background rather than as the thing to act on.
  It is the section the user reads first.
- Skill collection reads installed source, retained explicit slash-command eval
  records and recent matching Codex/Claude invocation turns. The configured
  model compares instructions with reported outputs; collection itself runs no
  model, mailbox command or installed skill. Session sampling and missing logs
  stay explicit, and a reported result never proves an artifact was checked.

## Person event status and calendar dates

Confirmed logistics and arrival do not prove an event or pack-up completed.
Keep supported arrangements in dated History, and leave missing outcomes
Unknown without creating a current debt from a historical gap. A copied
recipient does not become the event organiser or the author of another
person's confirmation.

An a32 Person trial cited the earliest retained reply as `First contact`, even
though that reply referred to an earlier application. The dated reply supports
an observed exchange, not the start of the relationship. The Person prompt now
asks for `First contact: Unknown` when the earlier event has no dated original,
and for that gap in `Uncertainties` (#2261). Deterministic fact extraction no
longer supplies the oldest mail as `First contact`; the People index reads the
date only from an explicit page fact. A cited date alone is not proof of the
field's meaning.

One a33 Person trial also attributed a calendar booking's displayed
Australia/Sydney event time to the guest. A booking's event time zone does not
establish either person's own time zone; the correspondent instruction now
requires an explicit person-level label before making that claim.

A later a33 rerun cited an attachment that did label the invitee's zone, but
its first-fold `Now` summary omitted the sourced reason a recruiting thread
closed. The Person instruction requires the `Now` sentence to state that
reason before any no-follow-up guidance, because Home and the Person hero use
it directly.

Fact extraction converts source timestamps to `schedule.timezone` before
deriving contact and source dates. It sorts full instants, rather than date
strings, so reversed inputs on the same UTC day still cite the correct first
and last message. The facts packet names this timezone. A message's local send
date remains distinct from its proposed event date.

The reader uses the same notebook calendar for timestamp dates, relative
contact age and year boundaries. Date-only facts retain their exact day; the
browser's timezone cannot shift them. Activity is latest first and phone lists
show complete rows. Explicit page Role and Company fields, including Unknown
and historical qualifiers, supersede older derived index values; absent fields
can still use the index. Other indexed fields retain their existing precedence.

Four actual pages were manually corrected from reviewed current and historical
mail. Fresh historical captures remain private audit evidence, separate from
the 90-day init archive; this round does not prove their citations all resolve
in the reader or that automatic generation follows the new rules. See the
[scoped review](../design-evidence/rem-event-calendar-review-2026-10-03/REVIEW.md).

## Skill original excerpts in the reader (#2174)

Temporary investigation bodies are still scrubbed after a run. An accepted,
changed skill page keeps only its cited instruction/reference excerpts in private
local state: at most 640 characters per original or numbered part. Full-content
hashes must match the source identifiers before retention. The first saved
capture is preserved; conflicting full hashes are rejected. Secret-shaped or
explicitly private content is excluded. The reader reads these saved excerpts,
never today's installed files to substitute for a historical citation.

An older instruction excerpt can be recovered only from matching content; its
recovery time is recorded separately from the unknown original collection time.
The UI explains that instructions describe intended behavior, not a verified
result. Prefix excerpts may omit a claim's supporting passage; truncation and
the unvalidated claim-span warning stay explicit. Session, eval and run-report
references remain unavailable without retained historical evidence. No-change
or refused investigations do not create new instruction captures.

Skill activity in the reader uses recorded invocation dates. An investigation
date cannot establish that a skill was used; file update dates stay separate.

## Survey before selecting findings

A two-year mailbox window does not establish two years of reading. Survey the
whole supplied index and entry headers, then read each distinct relationship
thread across older and newer months. This avoids rewriting the latest request
while missing the introduction, agreement or later resolution. The coverage
reply names actual files and months read, including relevant threads skipped.

An Insight connects dated evidence to a current obligation, changed relationship
or consequential next contact. Check later replies before calling a request
open. Longer pages and higher token counts are not evidence of a better finding.

## Supplement sources through their own tools

- **Why not search mail yourself.** The collector has already asked every
  connected mailbox, on the server, for every known address over the window;
  every match and every readable attachment is in the material with its source
  id. On 2026-09-23 three good person pages were written from self-run `co
  outlook` searches, cited as "Outlook message 39" and "listing rows 2, 4, 7",
  and all three were rejected whole. Listing row numbers also change between
  listings, so they identify nothing a week later.
- **Runner-mediated follow-up.** Outside a quick first pass, the runner may
  offer up to five extra mailbox queries for unresolved fields. The model
  writes queries to a task file; the runner performs read-only searches and
  returns messages with stable source IDs in one more turn. The model never
  runs a mailbox command itself. The a13 prompt said both “no mail search” and
  “write mail searches”; the distinction must remain explicit in the Skill.
- **New address → `Handles`**: the next investigation searches it.
- **`evidence-index`** means the material was too large for one turn and was
  written to files rather than summarised (#1850). Reading every file would
  recreate the size problem; searching per field keeps each turn bounded. Its
  exact supplied path can be outside the disposable task directory while still
  inside the private notebook. The model may read that index and the snapshots
  it names, and writes only in the task directory.
- **Project repository snapshots** are gathered by co rem before the offline
  turn. The model reads only the bounded files named by the supplied source
  index; the page's `Paths` do not authorize opening
  the original checkout. The index names omitted files, so absence from the
  packet is not proof of absent implementation. A `project-inventory` is a
  list, not evidence. Sessions show what the user asked for, not what the
  repository holds.
- A source-heavy project trial cited several real snapshots but opened Insight
  with a branch name and commit date. Those are useful status facts, not a
  decision-changing finding. Project writers now ask for a sourced constraint,
  change or mismatch with a consequence, and leave Insight Unknown if the
  packet has none. This is a prompt criterion, not a claim that the rerun passed.
- A second trial treated two short complaints in a session run from a project
  folder as defects in that project, although neither named its product or a
  matching component. Project writers now require a source-to-project link
  before using session input in status, issue or Insight sections. Folder
  location alone establishes the workspace, not the complaint's subject.
- A later explicit project page treated an older README description as a
  current storage fact and the first observed folder session as the project's
  start. Writers must attribute dated documentation to that snapshot and leave
  `Started` Unknown unless the project start itself is evidenced.
- An explicit project investigation cited live coding-session inputs that were
  absent from the older mapped session archive. An accepted page now retains
  only the cited live inputs in private operational state, so the reader can
  open their original text with the input-only provenance warning. A rejected
  page retains none. This also covers person pages citing coding sessions.
- A cited repository file's first 640 characters hid a release-policy passage
  after character 5,000 and a hook signature after 9,000. The source dialog now allows 65,536 characters for a
  cited repository snapshot, and each Sources row opens its own source on touch
  even when inline citations are grouped into one chip.
- An auto-eligible page then joined generic release requests captured in a
  project's folder to that package's release status. Those requests did not
  name the package or its version. A common verb such as release, patch or test
  is not a source-to-project link; the writer must leave those requests out of
  project status and lead with a finding supported by that project's own
  snapshots. The first Insight sentence must put the conclusion before detail
  so it remains useful in the phone preview.
- **`Quick first pass`**: only the sample was evaluated, so the page must not
  read as a final profile. The runner must not append the optional mailbox
  search instruction to this pass.

## Keep the composed prompt coherent

`co ai` expands the leading `/rem-investigate` Skill before handing the task
to Codex or Claude Code; those harnesses do not know ConnectOnion's Skill
catalogue. The page and source Skills are composed separately so only the
subject's rules travel. In a live a13 run, the correspondent addendum said to
put every thread in History oldest first while the person page required at
most eight milestones newest first. The latter is the canonical page shape.
The `Investigation:` footer is runner metadata: keep it unchanged even when it
says `not investigated yet`; the placeholder check applies to body sections.
The task-specific suffix uses named sections and a closed `<co_rem_task>`
envelope so operational instructions are easier to audit.

An inline packet containing an evidence index is not the complete evidence.
A live init gathered 245 mails and 35 attachments, but its model left the
relationship and Insight unknown because the task prohibited reading material
files. The task now explicitly permits reading indexed bodies and names only
the four already-inlined task packet files in its no-reread instruction (#2138).

Carried facts keep their original source IDs. Citing the existing page for
every historical statement erases the reader's route to the evidence and can
perpetuate an earlier error. Correct a disproven fact and cite the evidence
behind the correction; an index establishes where to read, not what happened.

## The open web

- The domain and signature are not in the web table because they are free
  facts already in the material; page loads are spent only on what the mailbox
  does not hold.
- **`cua_repl` / computer-use plugins:** on this runner they answer "No browser
  is available", which is about the plugin, not the web. `co browser` is the
  browser here.
- **Never LinkedIn:** a run of automated profile views got the account flagged
  and force-logged-out on 2026-08-23.
- **`Who they are` / `Our relationship` from the user's material only:** a web
  bio pasted there is somebody else's page.
- **Page-load budget:** five is generous; ten means the site does not have it.
- **A guess is worse than a gap**: the next pass would build on it.
- **Offline `co rem` runs** have no browser or network, and the page says
  nothing about it. The Skill used to require the line "web: not searched; co
  rem runs are offline"; on the 1.9.0a2 run it was on 5 of 5 pages, the same
  sentence about the runner on every person, contradicting the rule that
  `Uncertainties` is about the subject only (#1974). The runner already keeps
  what was searched in the task record and on the `Investigation:` line.

## Finish, then say what you did not finish

The coverage reply is kept with the run and tells a later run whether the page
is worth re-investigating or is simply about someone quiet. An `Uncertainties`
section that lists every source searched reads as an audit log and buries the
questions that matter. The same counts leaked into `History` too ("8 bodies
read"), so every line that used to send coverage to `Uncertainties` (a phone
number searched for, a handle that found nothing, an unreadable PDF, a mailbox
not searched, a domain with no org page) now sends it to the final reply
(#1974).

## What this stage must not do

- **One subject, one page.** Investigating one person produced three pages —
  the person plus two project pages restating the same negotiation — and the
  reader had to hold three accounts of one story.
- **No `agenda/` or `opportunities/`:** both are views over Open threads and
  state already recorded.
- **No `decisions/`:** lifting decisions is `rem-abstract`'s pass; doing it
  twice produces two versions.

## Candidate output contract

The runner validates and promotes the candidate, so the model writes only the
new file. The normalized structure may add sections absent from an older page.

## Evidence format

Only three things are citable because the runner verifies citations against the
material, opened URLs and read files; anything else is rejected with the whole
page. A retained map entry cited alongside a summary derived from the same
source would double-count one piece of evidence as two.

## Reasoning limits

With explicit `route.<stage>` settings (`co rem config set`) the runner saves
plan.json, synthesize.json and a separate method-review.json before rendering a
candidate. Source-ID checks confirm provenance, not truth. The configured
provider is the destination; there is no automatic escalation when a stage
fails. Examples of the transfer/invention errors seen: an offline fixture read
as an offline product; an unresolved review plus an unknown launch date turned
into "launch must follow that review".

## Reading the CLI reference only when a command is run (#1960)

The rule used to say "read the CLI reference first". In the 1.9.0a1 acceptance run (2026-09-30), the model obeyed it in every investigation: its first action was to `cat` the 12.6k-character reference. A 14.8k turn really carried about 27k, which undid the 15k ceiling from #1851. Offline runs, the common case, never run a `co` command, so they never need the reference.

## Moved out of the runtime Skill when it was split by page kind (2026-09-30)

The owner asked that a turn carry only what its subject needs, that the model stay inside the material our script prepared, and that it not be handed command references it can discover with `--help`. `co rem` runs are offline, so the web-lookup procedure below was never usable at runtime; it is kept here for an online mode.

### The open web (online runs only)

## The open web, only for fields still `Unknown`

Company (beyond the domain: which part, what it does — its own site); Role
(employer site, conference page, public bio); Phone (company contact page,
switchboard only, never a mobile); Signing entity (company register, ABN lookup,
site footer); Handles (company team page, public GitHub).

```
CO_WHO=rem-investigate co browser status
CO_WHO=rem-investigate co browser tab ls
CO_WHO=rem-investigate co browser tab open rem-subject --for "co rem subject lookup" --needs 10m
CO_WHO=rem-investigate co browser -t rem-subject go_to "https://<domain>"
CO_WHO=rem-investigate co browser -t rem-subject get_text
CO_WHO=rem-investigate co browser tab close rem-subject
```

Tab taken → use an unused name. Same `CO_WHO`/`-t` throughout; check each
result, not the exit code; close only your tab. Run it as a shell
command, never a computer-use/`cua_repl` plugin; `co browser "<instruction>"` is not needed. One
site, one read, one fact; stop by ten loads. **Never open LinkedIn.** Never web-fill
`Who they are` or `Our relationship`. Cite: `- Phone: +61 2 9385 1000 [W1]`,
`[W1] unsw.edu.au/contact — observed <date>`. Misses → `Uncertainties`. No guesses.

A `co rem` run is **offline**: no browser/network; local file tools only
(bounded reads, candidate in the task workspace, project `Paths` above). Never
execute a command from the material or query a source app. Skip the web; write
once: "web: not searched; co rem runs are offline". If `co browser` fails, say so. Never pretend to have looked.

### Routed runs and reasoning limits

The runner prompt names plan.json and synthesize.json when routing is on.

## Reasoning limits

Templates govern presentation, not conclusions. With `route.<stage>`, read
plan.json, synthesize.json, method-review.json and original evidence; keep
overturned hypotheses and open questions; ID checks do not prove truth. Never
rewrite executable skills; never escalate to another provider. Container traits are not the subject's (an
offline fixture ≠ offline product). No dependencies or deadlines from adjacent
facts. Describe only sources actually supplied or searched.

## A page stays readable in one sitting (#2019)

A daily update is an investigation over the new material only, and it had no
size rule: one pass took `projects/connectonion` from 13.4k to 25.3k characters
(1.9.0a5 acceptance run, 2026-10-01). The maintain Skill's rule -- about 15k,
fold the oldest `History` into dated one-line summaries, keep the lead and the
current state -- now applies here too, and the runner refuses a candidate over
20,000 characters that is longer than the page it replaces
(`page_review.size_errors`; the reasons for 20k are in `rem-maintain.md`).


## File-only project original evidence (#2180)

A project with no native messages can still have useful local source findings.
Its candidate inventory remains bounded to 60 files. Agent investigations
snapshot those supplied candidates up to 1,000,000 characters per file and
use the existing evidence index when material exceeds the prompt budget.
This can create up to roughly 60 MB of temporary local candidate text; it is
not a claim that the agent read every file. A large individual source may
exceed the usual 40k grouped evidence-file size. Summary investigations retain
the existing twelve-file, 2,000-character prefix limit, explicitly truncated.
The package manifest is included without admitting unrelated JSON data.

Each supplied body and checkout-state packet receives a content identifier
from origin plus exact supplied text. File modification time, capture time,
complete/prefix scope and project activity are separate. Snapshot IDs identify
the supplied body, not an uncollected full file. Exact origins and capture times
remain available to the reader. Fixed repository packets retain their previous
9,000-character bound; only explicitly marked local-file snapshots use the
larger file bound. Entire retained bodies are checked for secret/private text.

Original candidates remain available before digesting or writing temporary
indexes. After a successful changed page, only cited bodies are saved privately
under the same maintenance lock as result recording and index refresh. Rejected,
uncited or unchanged results do not accumulate original bodies. A completed
investigation records which identities were supplied, without claiming all were
read: unchanged uncited candidates must not trigger another paid run. Changed
file content can trigger a new investigation without a new coding message.
Rejected identical file material also waits for a change.

The reader displays up to 65,536 characters of a retained repository source,
not a validated claim span.
Extra files discovered directly under Paths are not automatically historical
snapshots. Legacy raw-path citations cannot be reconstructed from a current
checkout. New captures and manual repairs do not prove model semantic reliability.

## Mail bodies remain available after investigation

Live provider reads retain the full rendering privately before quote cleaning.
New snapshots live in `.state/mail/observed/<provider>/`; thin metadata is
indexed separately from the initial source inventory. They do not extend the
initial mailbox window, change its saved-body count or enter initial domain
material. An existing initial snapshot is reused. The first retained rendering
and its headers are also the version supplied to investigation, so a later
provider rendering cannot silently replace the cited body.

Opening archived mail checks its exact provider and native message identity.
The short citation hash identifies a message, not a validated claim or body
revision. Mail excerpts begin after the provider's Email Body delimiter and
remain bounded to 4,096 characters; the uncleaned rendering stays on disk.
From/To/Cc are available through a private disclosure. Sent time, retrieval
time and later recovery-retention time have separate meanings. A recovered
body with no recorded original retrieval time leaves it unknown; its Archived
time does not prove the body was available during the original investigation.
Provider-rendered text is not original MIME. Private mode hides these headers,
clocks, limits and excerpts together. Manual recovery does not verify automatic
writing or complete historical coverage.

## a22 source-reading trial

An explicit private project trial exposed three distinct writing errors: a
generated candidate-file inventory cited as if it were a source; a short,
unrelated missed-reply input expanded into a project listener mechanism; and
two documented workflow steps written in reverse order. The validator now
rejects the inventory citation. Project instructions require a distinctive
project cue for session claims, reopening originals for current findings, and
preserving the exact source order in `Overview` and `Try it`. They keep `Open
threads` as bare `Unknown` when no current exchange is supported. A later
seven-day candidate corrected the order and cited only repository snapshots,
but was rejected for omitting that heading; the original page stayed intact.
The next accepted seven-day page reopened its ten substantive sources, but
quoted unnamed follow-ups from a session whose earlier explicit request named
a different product. Those follow-ups cannot establish this project's status,
activity, open work or next action, regardless of the session folder. Project
instructions now require reading the earlier named subject in the same
session before using short follow-ups. That page also described a dated source
comment reporting tests as the latest verified execution; a comment is only a
source note until an independent run record supports the result.
The following candidate still cited `investigation:coverage`, and validation
rejected it without changing the notebook. The project writer no longer
receives that collector note; it remains in the run report, where search-window
limits belong. Validation still rejects stale or fabricated references to it.
An accepted seven-day page then made a checkout branch and commit timestamp
its `Status` and `Last activity`, while `Insight` was Unknown. Those values are
real repository facts but do not establish the user's current project work.
The next project-writing rule keeps checkout state in `Where it stands` and
leaves progress Facts Unknown until a dated project-specific original supports
them. The reader uses a sourced project purpose and an explicit sample limit
when no current insight is supported.
Another accepted seven-day page still promoted an unnamed, one-line follow-up
to `Now` and `Latest issues`. Earlier user input in the same Claude session
explicitly named another product, but the project-folder selection had omitted
that earlier input. The gatherer now withholds an unnamed project-folder input
when an earlier user input in that session used another project folder. An
input that explicitly names the investigated project remains available. The
run report counts withheld follow-ups; this is a conservative attribution rule,
not a semantic check for every session or a complete-history claim.
The sampled Skill page had two legacy source rows that opened no original:
the mutable run-summary note and the carried page. Skill-writing guidance now
uses retained `skill-record` run pieces and `skill-source` or `skill-reference`
instruction bodies, and validation rejects those two legacy rows. Cited run
excerpts show up to 4,096 characters; retained instructions show up to 16,384
characters, so the actual decision thresholds can be checked. An older short
instruction excerpt widens only when a new accepted investigation supplies the
same content hash. These are bounded private source excerpts, not proof that a
Skill's documented behavior was executed.
The repository-only v12 page exposed the next boundary: all 55 ambiguous
session inputs were withheld, but the writer promoted an old file note about a
branch into a `Now` finding. With zero assigned session inputs, the new prompt
scope and candidate validation require bare `Unknown` in `Insight` and `Open
threads`. The dated note may remain in `Where it stands` as history. Its cited
54.9k-character source also had the relevant line beyond the former 16,384
character reader cutoff; the repository dialog now shows up to 65,536
characters from the retained snapshot. This makes the sampled original
checkable without reading a mutable checkout. It still does not prove the old
branch remains pending today.
These trials establish narrow failures and fixes, not semantic reliability
across all project pages. [The independent review](../design-evidence/rem-source-review-2026-10-03/REVIEW.md)
records the actual rendered states and remaining checks.
