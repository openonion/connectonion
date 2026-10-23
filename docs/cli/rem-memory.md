# co rem reflections and investigation

co rem keeps raw evidence separate from the current interpretation. The preview adds
explicit commands for corrections, questions, connections and stage models.

## Record a correction

```bash
co rem reflect projects/aurora.md 'Still a prototype' --author user \
  --kind correction --previous 'Released' --basis 'No release tag exists' \
  --applies 'As of 2026-09-20'
co rem reflections projects/aurora.md
co rem reflections projects/aurora.md --compact
co rem sync
```

Both humans and agents supply their identity and basis. Records remain immutable
under `.state/reflections/`; supersession uses repeatable `--supersedes ID`.
A correction is not automatically true because it is newer or human-authored.
`--compact` creates a lossless columnar view under `.state/reflection-summaries/`;
it does not delete originals or claim semantic compression. Updates use a compact
view only when it reconstructs the retained records exactly and reduces serialized
context size; stale or altered views fall back to the originals. A task stops if
the resulting context still exceeds the budget.

### When feedback is processed

In the next preview candidate, normal `sync` selects attributed reflection
records and review decisions by their explicit target pages. It keeps raw
records in the maintenance input; changing the compact view is not a new event.
Fresh feedback bypasses an older page cooldown or ordinary source-current check.
Each target receives its own relevant feedback. A feedback batch is bounded by
the maintenance input allowance, page count and daily call allowance; oversized
feedback stays pending while ordinary captured material can continue.

An accepted page update or an explicitly accepted no-change turn records an
operational receipt under `.state/progress.json`, keyed by event content revision
and target page. A decision with two subjects is finished only after both targets
have accepted processing. A receipt does **not** establish that an assertion is
true. Refused, missing, over-budget and unattempted targets remain pending; inspect
`co rem logs` for `feedback_deferred` reasons. A zero-progress feedback batch reports
`deferred`, so `sync --all` stops instead of immediately buying the same work again.
The existing refusal interval and retry cap also apply to this path. New content
revisions are assessed separately from older consumed or refused revisions.

The native runner retains a small promotion proof before replacing an accepted
page, and after an accepted no-change turn. Recovery requires both the exact saved
page hash and the retained feedback revision before acknowledging the interrupted
turn. Daily maintenance retries use the same per-target receipts. Trusted custom
runner callbacks retain their existing interface, but cannot recover a crash
between their own page write and return without a native promotion proof.

Legacy consumed raw IDs remain an operational compatibility boundary, not proof
of correct application. A retained exact compressed summary can identify its raw
members. If an older consumed summary was overwritten, membership cannot be
reconstructed: affected unreceipted reflections are explicitly deferred for source
inspection, including newer records on that subject. The code does not guess which
old assertions were applied or silently replay the whole history. No automatic
legacy reconciliation command is included. No existing real notebook is migrated
or rewritten by installation.

## An unavailable source during sync

In the next preview candidate, a read or authorization-service failure from one
selected source keeps that source's cursor unchanged. Sync tries the remaining
selected sources until it finds material for its normal one-source-kind batch.
No new account, subscription or authorization is added by this fallback.

When that batch completes but another source could not be read, the run reports
`partial`, with `source_failures` and a warning in `co rem logs`. Only the healthy
source's accepted material advances. An explicit sync exits nonzero for partial
coverage; `sync --all` stops after that bounded batch instead of repeatedly trying
the unavailable source. Run sync again after resolving the reported source error.
If no material can be processed, collection reports `failed` without a model call.
The scheduled slot is served and status retains the attention warning.

The reader marks partial runs as needing attention in the night trace, morning
brief and Activity. Accepted page changes stay visible. Partial source coverage
does not produce an all-clear or a “nothing changed” claim, and source access
failures are not labelled as model authentication failures. Activity offers a
copyable command for the exact run log; private provider output stays out of the
brief. These reader states still require current native desktop/phone and
accessibility acceptance before release.

This describes sources attempted in that batch. It does not certify that every
subscription is caught up, that every page is accurate, or that an unavailable
provider has recovered. Installation does not rerun a failed real nightly pass.

## Investigate questions with explicit stage models

```bash
co rem config set route.plan default
co rem config set route.extract ollama/qwen3.5:9b
co rem config set route.synthesize default
co rem config set route.render default
co rem investigate projects/aurora.md
```

Setting any route opts investigations into plan → synthesis → candidate rendering.
Extraction runs when material exceeds the existing input budget, using its own
configured route. Unconfigured stages inherit the notebook's existing runner/model.
Inspect `co rem config` before choosing destinations: explicitly
routing a stage to a cloud harness permits that stage to read the supplied evidence.
There is no automatic provider escalation or retry loop. Run `co rem config set route.<stage> default` for each stage
to remove all overrides and return to single-pass investigation; `route STAGE --clear`
removes only that stage override.

Plans and findings live alongside task artifacts under `.state/tasks/`. Findings
retain before/after judgments, source IDs, unresolved alternatives, and concise
reasons. `method-review.json` is a candidate improvement, never an executable skill
rewrite. Original gathered evidence survives chunking under `.state/evidence/`.
Structural validation identifies missing citations; it does not establish truth.

## Review questions and candidate links

```bash
co rem propose link projects/aurora.md 'Do these share the same constraint?' \
  --related projects/storage.md --basis 'Compare the two recorded decisions'
co rem review
co rem review ID --verdict yes --author user --response 'Both require offline operation'
co rem review ID --verdict no --author user --response 'Different constraints'
```

For a `question`, pass one subject and later `--verdict answer --response TEXT`.
Decisions are retained in `.state/reviews.json`; exact rejected candidates do not
reappear. Maintenance receives answered/accepted/rejected records as evidence.
Models can propose at most two candidates per pass. The reader's **Questions &
connections** section displays them and terminal commands; it is a read-only snapshot.

Optional local voice input requires **whisper.cpp's `whisper-cli`** and an already
downloaded local model. Nothing is downloaded or sent to a cloud transcriber:

```bash
co rem review ID --verdict answer --author user \
  --audio answer.wav --local-model /path/to/ggml-base.bin
```

## Preserve sessions and run a daily round

```bash
co rem capture /absolute/path/rollout.jsonl --source codex
co rem capture /absolute/path/session.jsonl --source claude-code
co rem sync
```

Capture filters to recognized user messages using the existing source adapters,
writes a durable queue, and invokes no model or maintenance lock. Repeated capture
is deduplicated by source ID. If a bounded pass reports remaining bytes, capture
again before deleting the transcript. Hook installation is manual and depends on
the host's event contract; this command does not edit Codex/Claude configuration.

`daily` runs maintenance first, then at most one unfinished person/project/organization.
It reserves the remaining daily call allowance before investigation and fails closed
if extraction needs more calls. Reservations are conservative and survive crashes.
This is a call budget, **not a verified percentage of a subscription or dollar cap**.
Existing background schedules continue to run `sync`; `daily` is explicitly invoked.

Normal sync still requires recorded source consent. Captured material retains its
existing batch checkpoints; feedback uses the per-target processing receipts above.
An accepted target stays acknowledged if a later target fails. This preview
does not implement cross-machine locking, external sharing permissions or automatic
factual adjudication. The underlying Markdown pages remain local.
