# Wiki 1.8.7 requirement and verification map

Main review: #1454. Lifecycle: #1523. Product discussion: #1580.
Reader fixes from #1587 are included in the main PR. No release or merge is performed.

| Confirmed requirement | Implementation | Verification |
| --- | --- | --- |
| Init builds people/projects/skills before investigation | `wiki/map.py`, `wiki_commands.py`: deterministic init; metadata counts and coverage, stable source identities, existing pages preserved | `test_wiki_map.py`, CLI `test_init_builds_all_maps_without_model_or_investigation` |
| Existing skills remain in place | `skill_map.py`; inert source-linked catalog, distinct installations | `test_wiki_skill_map.py`, map repeat/source-byte test |
| Independent person/project/skill templates shared by map/investigate | `files.py`, bundled `wiki-page-*` Skills | `test_wiki_instructions.py`; legacy normalization test |
| Project opening: purpose, user-flow ASCII, real entry point; details later | `wiki-page-project`, canonical project skeleton | template shape tests; single-project acceptance below |
| Skill usefulness, run evidence, artifacts, problems and improvements | `wiki-page-skill`, `skill_runs.py` | `test_wiki_skill_runs.py`; explicit invocation/sample/model limits |
| No invented success rate or installation attribution | unassessed goals/quality; name-only attribution disclosed | skill-run tests for missing output, history and retained samples |
| Reliable write path | investigation writes new candidate; runner validates before replacement | candidate success/rejection tests; real single-page run |
| Old skeleton and current template agree | `page_review.normalize` adds missing headings while retaining prior text | legacy page idempotence/content test |
| Template examples never become facts | concrete person example replaced by empty shape; source-only instructions | shape checks and single-project review |
| Duplicate titles/headings and unresolved references rejected | `page_review.validate`; exact source definitions, runner-owned status | rejection tests; candidate remains local for diagnosis |
| Long JSON does not silently lose text | exact original plus paginatable readable representation with reversible string chunks | long escaped/unicode input reconstruction test |
| User intent is not completion | project/investigation instructions; evidence and uncertainty sections | synthetic request for an unimplemented hosted site |
| Real CLI/path instructions | bundled `wiki-init/CLI.md` included in composed instructions, explicit roots; separate email/Gmail/Outlook/browser usage | CLI help inspection; provider command tests |
| Reader content and navigation repairs | #1587 reader, browser tests | 14 tests pass in Chrome at 375/768/1440 widths; synthetic screenshots |

## Current boundaries and remaining work

- #1610 tracks question/correctable-hypothesis-driven investigation, staged deterministic/small/strong-model work and method review. It is follow-up design and implementation, not delivered here.
- #1611 tracks user corrections and agent reflection through one update mechanism: current notes + new material + relevant reflection, with layered compression preserving reasons, sources, time and uncertainty. Parameters remain undecided; no destructive source deletion or executable-Skill rewriting is introduced.


- #1580 is a discussion, not approval to implement a homepage redesign, sharing interaction, ongoing feed, or diary. Those remain outside this implementation.
- Init enumerates every correspondent without claiming they are a human; classification and importance ranking remain an explicit Skill step. It does not discard automated addresses by regex. Disabled mail sources remain disabled; missing sources are disclosed.
- Retained `.co/evals` YAML slash-command turns cover only a subset of skill calls. Deleted history and outputs cannot be reconstructed. No lifetime count, global success rate, or per-installation runtime total is claimed.
- Citation checks establish structure and identifiable references, not whether a sentence logically follows from evidence. Semantic truth and quality still require review; web URLs are recorded references, not proof of a successful fetch.
- Candidate files avoid the known write-existing/edit-match loop. The selected harness still has its own filesystem permissions; this is not an isolation boundary. A delegate that directly changes other files is reported, not silently rolled back.
- #1523's daily budget/round order and #1443's six configured slots need one settled contract. Hard percentage-of-subscription limits, daily investigation/maintenance interleaving, and a certified live-account initialization are not delivered here. No unattended queue was started.
- Programmatic mail reads retain the existing 200-message/seven-day-window limit. `co email` is documented for explicit retrieval but has no Wiki source adapter; sent listing lacks pagination. Jira is not integrated.
- The historical local-model overnight experiment is failure evidence: 52 queued, 3 attempted and failed, 0 accepted, 49 not attempted. No output was promoted, no private source or report is included here, and that queue was not restarted.

## Review sequence

Read the map tests and candidate rejection tests first, then the single-project
acceptance and browser checks. A mapped page, successful model process, accepted
structure, and factually reviewed result are four separate claims.

Detailed commands, actual Atlas output, usage, failed-attempt diagnosis and full
suite limits: [consolidated acceptance](../testing/wiki-187-integration.md).

## Next-batch implementation and quality evidence

- [x] Disposable single-page working copy; candidate validation and promotion
  under the sync lock with stale-snapshot rejection.
- [x] Relevant entity template only, with shared citation rules and CLI reference
  on demand; stage input-size, duration, usage and failure records.
- [x] Same-material comparison tool and explicit independent quality-review
  protocol; retain failed outputs and verify evaluator findings.
- [x] Synthetic project comparison reviewed after supplying complete original
  execution evidence; 363 focused tests pass.
- [ ] Repeat quality comparisons for people and installed Skills.
- [ ] Resolve corrections/layered updates and budget/round contracts before
  treating those follow-up designs as implemented release requirements.

Evidence and limitations: [comparison](../testing/artifacts/wiki187-next/README.md),
[protocol](../testing/wiki-quality-protocol.md). This does not authorize release.

## Organization map at initialization

- [x] First-stage init builds organization candidates from exact correspondent domains,
  including single contacts and notice-only domains, without model calls.
- [x] Known public mailbox domains excluded; candidate identity and employment remain
  unverified; no inferred company names or subdomain/domain merges.
- [x] Canonical org pages link to People; matching existing org pages and user edits
  remain intact. `notes/orgs-map.md` and `.state/map.json` retain the observed map.
- [x] Regression cases cover domain grouping, public mailboxes, invalid addresses,
  single contacts, notice-only subdomains, existing pages and repeat initialization.

See [initialization contract](wiki-init-contract.md). This map does not claim verified
organization membership or complete mailbox-provider classification.

Organization-init verification: `PYTHONPATH="$PWD" python -m pytest
tests/unit/test_wiki* tests/e2e/cli/test_wiki* -q` — 280 passed, 10 opt-in
browser skips. `python -m build --wheel --no-isolation` and `git diff --check`
passed. No model call, real-mail acceptance or release is claimed for this change.
