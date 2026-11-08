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

## Repository ingest (sprint 11)

The ingest contract is tested with `fernhill/lanterns` and fictional contributors.
The reader will read JSON at `.state/code/<owner>__<repo>/repository.json` only;
read-only acquisition and conservative session links are implemented separately
from snapshot rendering. Issues, PRs and runs are capped at 200/100/200 per sync.

`native_round.prepare()` refreshes once per round, under the existing maintenance
lock, after consented sessions are imported. It uses no model. It considers at
most 2,000 project pages and syncs at most three due repositories, oldest attempt
first. Private project pages are excluded. `sync_repository()` is also callable
explicitly under that lock. The canonical Facts `Repository: owner/repo` (or GitHub
URL) identifies the repository. No additional database or service account exists.
A Facts value that is not a canonical GitHub `owner/repo` (for example
`docs.site/guide`: GitHub owners have no dots) is skipped when collecting, with
`{"status":"skipped","reason":"not a canonical GitHub owner/repository"}` in the
round's result; its projection is `status: "invalid"` with the same reason. One
bad line no longer fails the whole round or the reader projection.

Each repository waits 30 minutes after its last attempt (including failure).
The round holds the maintenance lock while it reads, so it also has a time
budget: no new repository starts after 90 seconds (`CODE_ROUND_SECONDS`). One
repository is 7 gh calls (2 issues, 1 GraphQL, 2 runs, 1 releases, 1 tags) and
3 local git calls, each with a 20-second timeout, so the worst case is the
budget plus one repository's timeouts (about 90 s + 200 s), not three. Measured
(2026-11-08): the six REST reads of a large public repository took 9.4 s cold and
0.5 s when all six revalidated as 304; one round of three repositories on
realistic-size fictional data (200 issues, 100 PRs with 25 checks, 200 runs,
300 local commits, 500 session entries) spent 1.2 s locally. A notebook naming
34 repositories therefore needs 12 rounds before every repository has been read
once; later reads are mostly 304s.
GitHub reads use the owner's `gh` executable and its normal authentication:

- Issues: two GET pages of 100, all states, newest updated first; the GitHub REST
  issues endpoint includes PRs, which are removed after the bounded read. A
  200-item response is therefore not necessarily 200 issues.
- PRs: one fixed GraphQL query, newest updated first, at most 100; at most 100
  check contexts each, with the overall rollup state required to prove green.
- Workflow runs: two GET pages of 100, newest first.
- Releases and tags: one GET page of 100 each. These are bounded samples too.

There is no automatic pagination. The REST resources retain ETags and response
bodies in the same `repository.json`; subsequent due syncs send `If-None-Match`.
A 304 reuses the corresponding body, with the revalidation command/time recorded.
`gh api --include` exits 1 on a 304 (stderr `gh: HTTP 304`, gh 2.97.0, checked
read-only against a public repository), so `github_read()` reads the status from
the included headers and accepts a non-zero exit only when that status is 304;
every other non-zero exit is a failed sync.
GraphQL has no ETag and is read again. Each gh/git request has a 20-second timeout.
`github_read()` validates the **entire argv** against a closed allowlist of the
above GET endpoints or the exact fixed GraphQL query and owner/name fields.
Arbitrary queries, write methods, input files, alternate hosts and all other gh
subcommands (including comment/edit/merge/rerun) raise `GitHubReadRefused`
before spawning gh. It is a `RuntimeError`, not a `ValueError`, so a refusal is
never stored as a cache error and retried: our own argv breaking the allowlist
(say, a cap raised past the guard's two pages) is a bug and fails the round.

Successful cache replacement is atomic. On failure the last successful packet
and its `synced_at`/verification survive; `attempted_at`, `error`, and
`failed_verification` report the failed attempt. An initial failure has no
successful data. Absence, stale data, a failed request and a verified empty
bounded sample remain distinct. The packet's `coverage` contains caps, not
claims of exhaustive repository coverage.

`repository_projection()` reads the cache only. Every project record with a
canonical repo gains `repository`; missing cache gives
`{"repo":"fernhill/lanterns","status":"missing","joins":[]}`. A successful
packet exposes `schema_version`, `repo`, `status` (`cached` or `error`),
`attempted_at`, `synced_at`, `error`, `coverage`, and these arrays/objects:

- `issues`: number, title, state, label names, author login, `commentCount`,
  `updatedAt`, `closedAt`, `url`, and `milestone.dueOn`. URL/milestone preserve
  the existing issue priority, health and deadline projection. A synced cache
  wins over the legacy `.state/project-issues.json`, which carries no fetch time;
  an explicit in-memory `issues=` (just fetched by the caller) wins over both.
- `prs`: number, title, state, `headRefName`, `headRefOid`, additions, deletions,
  `closingIssues` (same-repository closing issue numbers), `mergedAt`, `createdAt`, `updatedAt`, `reviewDecision`, `authorAssociation`,
  author login object, `checkRollupState`, and `statusCheckRollup` contexts.
  Check runs carry name/conclusion/startedAt/completedAt; legacy status contexts
  carry context/state/createdAt. The context array is a bounded sample.
- `runs`: id, `workflowName`, event, branch, conclusion, `createdAt`, `headSha`,
  associated PR numbers in `prs`, and `completedAt`. For concluded runs,
  `completedAt` is REST `updated_at`: a conservative completion upper bound,
  not the exact last job finish time.
- `releases` and `tags`: bounded GitHub REST objects (including tag name and
  commit SHA, release tag_name/name/published_at/draft/prerelease).
- `pypi`: package, found, versions, or null when no package is declared.
  An explicit Facts `PyPI: lanterns` or PyPI project URL wins; otherwise local
  pyproject `[project].name`/`[tool.poetry].name` supplies the library name.
  PyPI uses HTTPS GET of `/pypi/<package>/json`, 20-second timeout and 4 MB
  response bound; a 404 is recorded as found=false. Remote-only library pages
  need the explicit PyPI fact. No version ordering is inferred from strings.
- `churn`: since/until UTC instants, commit cap (1,000), possibly_truncated,
  commits (sha/time), areas, session_links; null without matched local evidence.
  `local_status` distinguishes matched/not_configured/repository_mismatch.
  A local directory must be a Git root whose origin names the canonical GitHub
  repo. `git log --all --numstat --no-renames` covers the last 14 days by default;
  areas group by top path prefix (`(root)` for root files), with additions,
  deletions, changed-file occurrences and distinct commit counts. Binary files
  count as files with zero text-line changes. No claim about runtime follows.

The existing `.state/sessions.json` file entries retain `code_evidence`, populated
by consented import: exact cwd, start/end UTC instants, session ID and
`printed_commits` — the `[branch sha]` records git printed in that session's own
tool output. Mixed-cwd sessions are excluded. The session format version is not
bumped: an index written before code evidence existed is backfilled only for
transcripts modified within the 14-day churn window, so upgrading does not
re-import 180 days of sessions.

A session links to a commit only when **all** of these hold: the session printed
that commit's SHA verbatim (an abbreviated SHA of 7+ hex characters is a prefix
of the full one); the session cwd resolves **exactly** to the repository root or
a path in `git worktree list --porcelain`; and the commit time is not before the
session start. A time window alone is not evidence: it linked a worktree session
to commits the main checkout made meanwhile. There is no end bound or grace: the
printed SHA already shows the session saw the commit's creation, and the
recorded end is the last reply, not the last tool output. Subdirectories, sibling
repositories, a missing start, requested-but-unprinted branches and text
similarity never qualify. A link carries the printed branch. It is evidence the
session's own tool output showed the commit being made, not proof of authorship.
Shared projections (`local=False`) omit churn.session_links and replace every
absolute path a recorded command named (`git -C /home/…`) with
`<local repository>` wherever it appears, including `verification`,
`failed_verification`, join verification and error text. All stored times are UTC; views
convert for display using the notebook timezone.

`joins` is computed without a model, each with kind, bounded=true and
`verification: [{command: [argv...], ran_at: UTC, resource: ...}]`. These exact
commands and execution times are the data for the page's 「核对」 line:

- `merges_after_green_deploy`: the latest successful production deploy and the
  PR numbers merged after its completion bound. A production deploy is a workflow
  named /\bdeploy/ (not "preview" or "staging") that ran on a `push` to the
  repository's default branch (GraphQL `defaultBranchRef`, cached as
  `default_branch`) or on a `push`/`release` of a sampled tag. A feature-branch
  `workflow_dispatch` or a "Deploy preview" no longer counts. `basis` is the
  string the 「核对」 line prints with the commands, e.g.
  `Deploy · push · main · completed 2026-11-08T10:05:00Z`, so the reader sees which
  event and branch the claim rests on. Missing deploy evidence (including an old
  cache without `default_branch`) leaves deploy=null, basis=null and prs=[]. It
  does not prove deployment contents or environment.
- `failed_release`: failed runs of a workflow named /\b(release|publish)\b/ that
  is not a drafter, triggered by `release` or `workflow_dispatch`, or by a `push`
  of a tag (a sampled tag name, or a version-shaped ref that is not the default
  branch). "Release Drafter" on main and "prerelease checks"/"Release checks" on
  pull requests are excluded. Each entry has run ID, matching tags (same SHA or
  exact branch/tag), tag_present, pypi_present. PyPI presence compares tag
  without leading `v` to a published version; null means no PyPI observation,
  false means absent from the supplied version list. Tag absence is only absence
  from the bounded tag sample.
- `merged_closes_open_issue` (formerly `merged_title_open_issue`; the UI must use
  the new name): pairs of merged PR and still-open issue where the issue is one of
  the PR's GraphQL `closingIssuesReferences` **in this repository** (first 10,
  cached per PR as `closingIssues`). A literal `(#N)` in a title is no longer read:
  forward-ported titles name issues of the repository they came from.
- `green_unmerged_age`: open PR numbers, green_since (latest supplied check
  completion), age_hours, and as_of. Overall rollup SUCCESS and successful or
  neutral/skipped supplied checks are required; missing checks/times produce
  no age claim. Age is observed check age, not an uninterrupted-green history.
- `zero_comment_issues`: count and numbers of sampled open issues with zero comments.
- `external_action_required`: exact PR-number or head-SHA joins between action_required
  runs and PRs with association NONE/FIRST_TIMER/FIRST_TIME_CONTRIBUTOR/CONTRIBUTOR.
  This is an association category, not a claim about a person's identity.

A fictional projection fragment (the packet also contains the arrays above):

```json
{
  "repository": {
    "repo": "fernhill/lanterns",
    "schema_version": 1,
    "status": "cached",
    "synced_at": "2026-11-08T12:00:00Z",
    "issues": [{"number":7,"title":"Cedar light","state":"OPEN",
      "labels":[],"author":"mara-quill","commentCount":0,
      "updatedAt":"2026-11-08T11:00:00Z","closedAt":null,
      "url":"https://github.com/fernhill/lanterns/issues/7","milestone":{"dueOn":null}}],
    "joins": [{
      "kind": "zero_comment_issues", "bounded": true, "count": 1, "issues": [7],
      "verification": [{
        "command": ["gh","api","repos/fernhill/lanterns/issues?per_page=100&page=1&state=all&sort=updated&direction=desc","--method","GET","--include"],
        "ran_at": "2026-11-08T12:00:00Z", "resource": "issues", "status": 200
      }]
    }]
  }
}
```

This is the projection contract for the separate UI branch; `reader.html` is
unchanged. A rendered page has not been reviewed in this data-only worktree.

PRs also expose `checksTruncated` from the context connection's pageInfo. A
successful overall rollup proves status, but a truncated context sample cannot
establish the latest green timestamp: such PRs are excluded from green-age joins.

An existing ordinary directory in Paths is treated as a repository mismatch;
its lack of Git metadata does not discard successfully acquired remote evidence.
