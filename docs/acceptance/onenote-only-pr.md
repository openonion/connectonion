# OneNote extraction and upstream forward-port acceptance

## 2026-11-20 forward port

The replacement for openonion/connectonion#3218 starts from upstream main
at `0a0964ba3a4d1edd45a7e78b4623e50d5db82c14` (1.9.6rc41).
The Reader evidence navigation and project activity, and the runner's current
scope and promotion checks, stay in place. Reader evidence uses REM's
`KEY_SHAPES` detector. A record containing a recognized credential shape
is refused before model handoff, and a synthetic regression checks that the
Reader withholds it and the original snapshot stays intact.

The macOS checks used CPython 3.12.9, Node 22 and an isolated home.

```sh
uv sync --locked --extra dev
python -m pytest tests/unit/test*onenote*.py tests/unit/test_rem_service.py \
  tests/unit/test_rem_runner.py tests/unit/test_rem_page_review.py \
  tests/unit/test_rem_project_claim_review.py tests/unit/test_rem_reader*.py \
  tests/unit/test_init_rem.py tests/unit/test_provider_credentials.py \
  tests/unit/test_uniform_provider_errors.py tests/unit/test_rem_help_moves_nothing.py \
  tests/unit/test_cli_help_contract.py tests/unit/test_every_command_has_a_next_step.py \
  tests/unit/test_cli_tips_name_real_commands.py -n 4 -q --tb=short
uv build --offline
git diff --check
```

Benchmark schema checks passed for `onenote` (7 cases),
`onenote-remediation` (5), and `onenote-rem-workflow` (6). To reproduce,
copy their YAML files into an isolated `.co/benchmarks/` and run
`co benchmark check NAME --json` for each. The deterministic pytest coverage
exercises the CLI commands, source intake and citation contracts. No live skill
eval or semantic model scoring was run.

Chrome inspection used a synthetic Knowledge page with a pinned OneNote source.
The evidence drawer showed the title, date, excerpt and original link on desktop
and at 390 × 844. Closing the mobile drawer restored navigation. An independent
AI reviewer inspected the conflict resolutions and sampled Reader states.

The record below applies to the earlier team candidate at `3f1396a`.
Its live Microsoft CLI screenshots are attached to
[team PR #3](https://github.com/Uncle-Daryl-Li/connectonion/pull/3#screenshots).
Live Graph acceptance, actual timer dispatch and real model quality remain open
for the forward-port head. Human review and upstream CI are pending.

## 2026-11-14 team candidate

Date: 2026-11-14. Platform: macOS, Python 3.12.9.

Base: upstream/fork `main` at `a32a7dceccf54050a73daeba9341bd58ad0591a1`.
Team source: `feature/onenote-source-20261106` at
`8e5241dcd8fe07111e87beb77a4289e258c78f29`.
The fork was fast-forwarded to the public upstream baseline with owner approval.
No sibling feature branch was merged. The PR records the exact tested code SHA.

The extraction retains OneNote source collection, local version storage,
metadata-only scope connection, approved native init/sync intake, immutable
Reader/claim-review evidence and the existing browsing/create commands. Shared
files were forward-ported in small hunks. Every modified pre-existing file was
matched by Git blob hash to the public baseline. No Jira/Granola implementation,
new third-party dependency, scheduler, Reader category or global page template
was introduced.

## Current automated verification

```sh
uv sync --extra dev
python -m pytest \
  tests/unit/test_onenote.py \
  tests/unit/test_onenote_source.py \
  tests/unit/test_onenote_source_auth.py \
  tests/unit/test_onenote_source_commands.py \
  tests/unit/test_onenote_source_scope.py \
  tests/unit/test_onenote_remediation.py \
  tests/unit/test_rem_onenote_imports.py \
  tests/unit/test_rem_onenote_remote.py \
  tests/unit/test_rem_onenote_citations.py \
  tests/unit/test_rem_service.py \
  tests/unit/test_rem_runner.py \
  tests/unit/test_rem_page_review.py \
  tests/unit/test_rem_project_claim_review.py \
  tests/unit/test_rem_reader.py \
  tests/unit/test_rem_reader_model.py \
  tests/unit/test_rem_reader_lazy.py \
  tests/unit/test_rem_reader_design.py \
  tests/unit/test_rem_reader_threads.py \
  tests/unit/test_rem_reader_sessions.py \
  tests/unit/test_rem_help_moves_nothing.py \
  tests/unit/test_cli_help_contract.py \
  tests/unit/test_init_rem.py \
  tests/unit/test_provider_credentials.py \
  tests/unit/test_uniform_provider_errors.py -q --tb=short
uv build
```

Initial focused result: **1,366 passed, 1 skipped**, 96.05 seconds. The skipped test aggregates
separate CI help-audit shards; this unsharded run audited the complete CLI tree
itself. Development dependency sync and wheel/sdist build succeeded. Read-only
`git diff --no-index --check` compared each changed file with the pinned archive
baseline; no whitespace findings remained.

Tests ran with an isolated HOME/configuration, no inherited operator credentials
and a synthetic managed-key placeholder. Graph responses and model callbacks
were test doubles. The repository's real-home/process leak guards remained
enabled. Early forward-port/help/test-harness failures were corrected; the final
relevant suite has no remaining failure. This is not a claim that every repository
test, real provider, operating system or model was tested locally.

## CI integration follow-up

The first full GitHub run caught two introduced CLI integration omissions outside
that initial focused command: five OneNote source leaves lacked next-step table
entries, and a root-help sentence was parsed as a nonexistent command by the tip
sweep. The correction registers each leaf as HANDLER (the existing handler already
prints the contextual next step) and describes bare invocation without embedding
command-shaped prose. No test or gate was disabled.

```sh
python -m pytest tests/unit/test_every_command_has_a_next_step.py tests/unit/test_cli_tips_name_real_commands.py tests/unit/test_onenote_source_commands.py tests/unit/test_onenote_remediation.py -q --tb=short
python -m pytest tests/unit/test_cli_help_contract.py -q --tb=short
```

Follow-up results: **1,928 passed** in 40.21 seconds; complete help audit **3 passed,
1 skipped** in 47.39 seconds. The skip is the CI-shard aggregation check described
above. A separate AI reviewer rechecked these exact registry/help changes and
reported no findings. These follow-up results supplement the original focused
service/Reader/source verification; they are not a new run of every repository
test. The subsequent GitHub head run supplies the cross-version full-suite result.

## Live Microsoft acceptance

The account holder explicitly authorized testing in the logged-in OneNote
account. A separate acceptance section and synthetic page were created through
the browser. Existing Microsoft CLI authorization was verified and the exact
browser-created section/page was located through metadata before body reads.
No unrelated page bodies, attachments or notebook content were collected.

Fourteen real CLI invocations covered:

- Source `verify`, `notebooks`, `sections`, `pages`.
- Existing `ls`, `pages`, `read`, and `create` in the dedicated test section.
- Daily import: 1 newly written, 0 skipped.
- Unchanged full reread: 0 newly written, 1 skipped.
- One-off export: 1 newly written, with the exclusive export preserved.
- Duplicate export and unknown section: expected exit 1 and recovery guidance.
- Invalid page limit: expected exit 2 and privacy-safe parser guidance.

Native intake used the real Graph transport and an explicitly **fake model
callback**. The first ordinary REM sync read 1 item; an unchanged repeat read
0 items, with exactly one callback. After a browser edit to the same selected
page, ordinary sync read 1 changed item and an unchanged repeat read 0. The old
pinned snapshot still resolved. No LLM was called and no timer was installed.
Safe count-only receipts are included as JSON evidence.

Local screenshots render actual captured CLI output. Notebook/page/account identifiers,
listing IDs, URLs and local paths are replaced with placeholders; unrelated
metadata rows are omitted where indicated. These are redacted transcripts, not
unmodified terminal-window photographs. Synthetic help/error coverage additionally
executed 30 invocations/listings through the actual CLI with replaced Graph
transport, including simulated create and partial failures. Reproduce that
credential-free capture with:

```sh
python scripts/validation/onenote_acceptance.py --output ./acceptance-output --screenshots
```

Never publish raw credentials, account IDs, notebook IDs, actual note archives or
authorization paths. The team candidate includes redacted transcripts/count
receipts and synthetic fixtures. The team PR description contains the seven
redacted screenshot groups. Local live archives remain outside the PR.

## Reader and independent review

The live-intake test page remained in the existing Notes/Activity path. Its
source drawer showed the pinned local excerpt and the safe OneNote original-link
entry. Desktop and 390×844 mobile states were inspected, including opening and
closing the source drawer. A mobile tabbar overlap found during review was fixed
by hiding navigation only while the evidence sheet is open and then rechecked.
API-only, unsafe, missing and unreadable link states were executed through the
current Reader JavaScript in isolated tests.

A separate AI reviewer inspected the scope/dependencies, code and supplied
desktop/mobile screenshots. Two code findings (mail-scoped consent fingerprint
context and connection metadata in Reader projection) and the mobile overlap
were fixed and rechecked. This was an AI role review, not a human founder review,
and sample coverage is not an all-page visual pass.

## Draft-to-ready conditions

- Run real model semantic-quality acceptance on dedicated synthetic notes:
  categories, attribution, uncertainty, appropriate reuse of existing pages and
  source-supported project relationships. The fake callback does not prove this.
- Observe an actual existing REM timer dispatch in an authorized test setup.
  Mocked due-slot dispatch tests passed; no real schedule was installed here.
- Review final GitHub CI, including Windows and other Python versions; the local
  macOS result does not establish those platforms.
- Complete maintainer review of the forward port and release/version decision.

The PR remains Draft until these outstanding acceptance gates are completed.
