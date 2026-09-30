# Why `rem-investigate` says what it says

The runtime Skill `connectonion/useful_skills/rem-investigate/SKILL.md` holds
only the rules, because it is re-sent on every model turn and every Codex tool
round of a co rem investigation (#1851). This file holds the reasons, incidents and
examples behind those rules. It is not loaded at runtime. When you change a rule
there, update its reason here in the same change.

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
- Skill catalog pages use a deterministic run-evidence path that reads retained
  explicit slash-command invocations without opening mail or running a model.

## Supplement sources through their own tools

- **Why not search mail yourself.** The collector has already asked every
  connected mailbox, on the server, for every known address over the window;
  every match and every readable attachment is in the material with its source
  id. On 2026-09-23 three good person pages were written from self-run `co
  outlook` searches, cited as "Outlook message 39" and "listing rows 2, 4, 7",
  and all three were rejected whole. Listing row numbers also change between
  listings, so they identify nothing a week later.
- **New address → `Handles`**: the next investigation searches it.
- **`evidence-index`** means the material was too large for one turn and was
  written to files rather than summarised (#1850). Reading every file would
  recreate the size problem; searching per field keeps each turn bounded.
- **Project `Paths` limits** (four levels, twelve files, no hidden files or
  credentials) keep an offline run from sweeping private data. A
  `project-inventory` is a list, not evidence. Sessions show what the user
  asked for, not what the repository holds.
- **`Quick first pass`**: only the sample was evaluated, so the page must not
  read as a final profile.

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
- **Offline `co rem` runs** have no browser or network; saying so once stops
  a reader wondering whether the web was tried.

## Finish, then say what you did not finish

The coverage reply is kept with the run and tells a later run whether the page
is worth re-investigating or is simply about someone quiet. An `Uncertainties`
section that lists every source searched reads as an audit log and buries the
questions that matter.

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
