# REM project data for views

`reader.snapshot()` enriches each existing project record in memory. Markdown,
record paths, titles, text, relations, coverage and other existing fields remain.
The same Python projection serves local and shared snapshots; JavaScript does not
need to infer priority or debt direction. No model, network call, page write, state
initialization or automatic merge happens while building a snapshot.

```json
{
  "path": "projects/harbour.md",
  "title": "Harbour",
  "priority": 2,
  "score": 12.5,
  "reasons": [
    {"text": "paying client: 5 × 1.5; ...", "points": 7.5,
     "source": "gmail:request", "cite": "1", "path": "projects/harbour.md",
     "sources": [{"source": "gmail:request", "cite": "1", "path": "projects/harbour.md"}]}
  ],
  "health": "at_risk",
  "health_reason": {"text": "A human has waited over fourteen days on an open obligation.",
                    "source": "gmail:request", "cite": "1", "path": "projects/harbour.md"},
  "kind_counts": {"owed": 1, "waiting": 0, "agent": 2, "answerable": 0},
  "parent": null,
  "same_as": [],
  "promised": [{"date": "2026-11-20", "text": "by 2026-11-20",
                "source": "gmail:request", "cite": "1", "path": "projects/harbour.md"}],
  "started": "2026-04-03",
  "last_activity": "2026-11-01",
  "date_sources": {
    "started": {"source": "codex:session:1", "cite": "2", "path": "projects/harbour.md"},
    "last_activity": {"source": "gmail:request", "cite": "1", "path": "projects/harbour.md"}
  },
  "pinned": false,
  "open": [{
    "text": "You owe Fern the report. [1]", "kind": "owed",
    "kind_reason": "explicit owner/counterparty direction", "needs_review": false,
    "who": "people/fern.md", "since": "2026-11-01", "due": "2026-11-20",
    "sources": [{"source": "gmail:request", "cite": "1", "path": "projects/harbour.md"}],
    "promised": [], "answer": null
  }]
}
```

The example illustrates field types, not a complete score calculation. All dates
are ISO calendar days or `null`. `promised` retains yearless or invalid written
dates as `{date: null, text: ..., source, cite, path}`. Day-month and month-day forms use a year only when a cited source has a dated timestamp; they never use the runtime year.
`reasons` contains at most three entries, ordered by contribution; `score` includes
all components, so these three entries need not sum to the total. Every reason
has a source, including a page-section anchor when no numbered citation exists.
`cite` is local to `path`; never resolve a bare citation number across pages.
`open` and `kind_counts` also appear on person and organisation records.

People/org obligations join projects by task links/names, cited sources or provider-scoped
conversation IDs, declared counterparty Facts Project(s) links, then a unique shared
organisation. Joined items retain `joined_from` and `project_match` evidence; ordinary
lowercase nouns require project/repository wording or code quoting. Ambiguous organisation
portfolios do not multiply a debt across projects. Organisation-only joins carry
`project_match.needs_review: true`; they do not affect scores/health and remain
review candidates. Project counts include these suggestions, so they must not be
reported as confirmed ownership. `inferred_projects` on the snapshot
(and counterparty record) contains unmatched confirmed owed items with `title`, `record`,
`text`, `kind`, `evidence`, `promised`, `suggestion` and `needs_review`; these are review
candidates, not created notebook pages or guaranteed distinct projects. Candidates
carry the same score, priority, reasons, health and date fields, plus tentative
`project_candidates` paths. Candidate counts can overlap tentative project joins.
`written_deadlines` preserves explicit dated context from Facts/Terms/At stake/Where
it stands, separately from an open action's `due` and `promised` fields. The current
reader UI does not yet render these enrichment fields.

Source entries, counterparty names and project aliases are indexed once per snapshot;
enrichment reads no archive and stores no cache in the notebook.

## Obligation classification, in order

1. Parse the existing `Open threads` list using the census parser, preserving its
   multiline items and excluding calm/Unknown placeholders. Local snapshots also
   honour existing done/skipped decisions, including returned items.
2. Resolve explicit person/org links, then unique exact page-title mentions. An
   ambiguous name does not identify a person. `who` is a notebook path, or `null`;
   a person/org page itself supplies the counterparty if none is named.
3. Explicit instructions addressed to agent/Codex/Claude are `agent`. An owner
   request (`The user asked/requested/wanted/proposed`, etc.) with a coding-session
   source and no human addressee is also `agent`; `asked:` is an explicit session
   instruction signal. Mentioning someone as a recipient inside an agent task
   does not make them the executor.
4. Otherwise the existing census direction rules decide `owed` (you owe, promised,
   must, someone requested your reply) or `waiting` (you asked a person, they owe
   you, awaiting their reply). Chinese directional phrases are recognised too.
   A human addressee takes precedence over the fact that the source is a session.
5. A session-sourced action without a human counterparty is `agent`. An unspecified
   project action also falls back to `agent`, with `needs_review: true`. A human
   page obligation with unspecified direction falls back to `owed`, also flagged
   for review. These fallbacks are coverage choices, not evidence of direction.
6. Only an agent query can become `answerable`: a matching cited assertion must
   already occur outside Open threads/Sources/Uncertainties on the project page,
   or in a retained context cited by the page. All nontrivial task terms and explicit dates must match, with at least two terms (or a shared
   Chinese phrase of at least four characters), an assertion, and a number for
   quantity questions are required; date/identifier digits and negated statements do not count. Repeated questions, unknown/unverified claims
   and input-only contexts do not qualify. Current/relative-time questions stay
   `agent`; an old count cannot answer “last night”. The matching text and exact
   source are retained in `answer`. This is a conservative lexical heuristic,
   not semantic proof, and it never closes or edits the original obligation.

## Priority calculation

Priority uses Linear's scale: **0 none, 1 urgent, 2 high, 3 medium, 4 low**.
The brief specifies the score formula, but not band boundaries. This implementation
uses `score >= 20 → 1`, `>= 10 → 2`, `>= 5 → 3`, positive `< 5 → 4`, zero → 0.

- Debt: highest **three** weighted open obligations, following the PM brief's
  inclusion of human obligations and incoming debts in the same capped component.
  Paying client = 5, partner/investor/event organiser = 3, student/capstone = 2,
  waiting = 0.5. All agent instructions together contribute at most 0.5, without an age multiplier. An unclassified human waiter gets 1 with that exact
  label. Roles must occur in the obligation or linked counterparty Facts; role
  evidence is included in the reason's `sources`. Answerable items contribute 0.
- Time multiplier: overdue = `min(5, 3 + 0.5 * floor(days_overdue / 7))`;
  due within seven days (including today) = 2; later deadline = 1. Without a
  deadline, wait >14 days = 1.5, >7 = 1, otherwise = 0.5. Unknown age uses 0.5.
- Deadline: nearest written delivery/obligation/milestone within seven days +4,
  within fourteen days +2; counted once. Overdue pressure comes from debt/health.
- Money: explicit unpaid/unissued invoice, outstanding contractual payment or paid
  subscription +4; explicitly AUD/A$ amount above 10,000 +6, counted once. No
  currency conversion or assumed meaning of a bare `$`. Closed obligations do
  not re-enter through raw Open threads. Unscoped mail excerpts do not create
  financial pressure: a company biography describing paying clients is not an
  outstanding payment in this project.
- Issues: each open `priority:high` or `bug` updated within thirty days adds 1,
  capped at 4; a doubly labelled issue counts once. Unlabelled issues add 0.1,
  capped at 1. Other labels, missing update dates, closed or stale issues add 0.
- Momentum: dated project activity within seven days adds 1, at most once.
- Explicit completed Status sets the score to zero. Manual overrides apply last.

Sort by `pinned` descending, then score descending; do not sort priority ascending
without treating zero as “none”. This layer does not deduplicate debts between
suggested duplicate pages or roll child scores into parents.

## Manual state

Local snapshots read `<notebook>/.state/project-overrides.json`:

```json
{
  "projects/harbour.md": {
    "pin": true,
    "snooze_until": "2026-11-20",
    "at": "2026-11-08"
  }
}
```

An active snooze wins over pin, sets score/priority to 0 and `pinned: false`.
It expires on the stated day. Pin sets priority 1 and `pinned: true`, retaining
computed score. Both add an explicit owner-decision reason with a state-file
source. Shared snapshots do not disclose or apply private overrides/completion
state. This module only reads this file; the UI's future mutation endpoint owns
writing it. No real owner state was written during development.

## Health and dates

Health is computed separately from presentation priority: an overdue unresolved
obligation or open milestone is `off_track`; a deadline within seven days, a recent
open bug/high-priority issue, or a human waiting over fourteen days, or a recorded unresolved blocker is `at_risk`.
Absent those risks, no dated activity within thirty days is `quiet`; recent dated
activity is `on_track`. The sentence describes the available evidence, not a
forecast or guarantee. Pinning/snoozing does not erase underlying health risks.

`started` comes only from explicit Started facts. `last_activity` preserves an explicit project Last activity fact. Otherwise it uses
the newest dated Where it stands entry, mapped Last seen field or cited context time.
File mtime and investigation time do not count as project activity (this replaces
the previous census fallback for this project field). Dates are never fabricated
from today's date or inferred from a yearless phrase. `since` uses explicit
requested/since dates, a dated item prefix, or cited message times. Explicit
ISO/Chinese dates and English full-month dates with a year support promises;
yearless full-month/Chinese dates remain unplaced. Mail promises must share task
terms in the same sentence; quoted lines and conventional quoted-history blocks
are excluded. This deliberately leaves ambiguous natural-language promises out.

## Suggested project tree

`same_as` is an array of suggestions with `path`, `suggestion: true`, `reason`,
`source`, `cite`, `via`. Signals are exact canonical repository, exact Website/Domain
or normalised case/punctuation-insensitive title. In tree suggestions only, `path` is the target and `cite` resolves against `via`, the originating page. Shared domains are only hints,
not proof that two projects are identical. `parent` is one suggestion or `null`:
explicit “part of / subproject of / parent” links win; otherwise component repo
names (`oo-*`, `co-*`, docs-site/browser/handoff) can attach to the unique explicitly
named main product with the same GitHub owner, or a named “backend/frontend/component/service/docs for” relationship under that owner. Ambiguity and cycles leave parent
empty. No pages, IDs, counts, files or relationships are merged automatically.

## GitHub inputs

Snapshot reads existing cited GitHub context with explicit `State`, `Updated`,
`Labels`, `Title` lines, or an optional `.state/project-issues.json` mapping from
canonical `owner/repo` to issue objects (`url`, `title`, `state`, `updatedAt`,
`labels`, `milestone.dueOn`). An explicitly supplied `issues=` mapping takes the
same shape. Missing/stale metadata is not represented as a verified clean backlog.

`project_issues.fetch_project_issues(records)` is an explicit **read-only** gh
GraphQL adapter for pages naming a canonical repo. It paginates open issues,
retains update dates/labels/milestones, returns an in-memory mapping, and raises
on lookup failure. It does not save or initialize state; snapshot never calls it
implicitly. An external refresh job can supply the result to `enrich_records`.

## Validation and rollout

Tests use fictional projects and people. See `tests/unit/test_rem_project_data.py`
for snapshot integration and scoring/classification/date/state boundaries. Real
notebook audit results and their dataset limitations are in the separate report;
real people and project examples do not belong in source code or fixtures.
This change delivers the data contract only; the parallel designer owns screens.
The wiki and docs website should link to this contract when those views ship.
