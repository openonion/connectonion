# Wiki reflections and investigation

Wiki keeps raw evidence separate from the current interpretation. The preview adds
explicit commands for corrections, questions, connections and stage models.

## Record a correction

```bash
co wiki reflect projects/aurora.md 'Still a prototype' --author user \
  --kind correction --previous 'Released' --basis 'No release tag exists' \
  --applies 'As of 2026-09-20'
co wiki reflections projects/aurora.md
co wiki reflections projects/aurora.md --compact
co wiki sync
```

Both humans and agents supply their identity and basis. Records remain immutable
under `.state/reflections/`; supersession uses repeatable `--supersedes ID`.
A correction is not automatically true because it is newer or human-authored.
`--compact` creates a lossless columnar view under `.state/reflection-summaries/`;
it does not delete originals or claim semantic compression. Updates still read
original records and stop if the context budget cannot fit them.

## Investigate questions with explicit stage models

```bash
co wiki route plan --runner codex --model default
co wiki route extract --runner coai --model ollama/qwen3.5:9b
co wiki route synthesize --runner codex --model default
co wiki route render --runner codex --model default
co wiki investigate projects/aurora.md
```

Setting any route opts investigations into plan → synthesis → candidate rendering.
Extraction runs when material exceeds the existing input budget, using its own
configured route. Unconfigured stages inherit the notebook's existing runner/model.
Inspect `co wiki route` and `co wiki config` before choosing destinations: explicitly
routing a stage to a cloud harness permits that stage to read the supplied evidence.
There is no automatic provider escalation or retry loop.

Plans and findings live alongside task artifacts under `.state/tasks/`. Findings
retain before/after judgments, source IDs, unresolved alternatives, and concise
reasons. `method-review.json` is a candidate improvement, never an executable skill
rewrite. Original gathered evidence survives chunking under `.state/evidence/`.
Structural validation identifies missing citations; it does not establish truth.

## Review questions and candidate links

```bash
co wiki propose link projects/aurora.md 'Do these share the same constraint?' \
  --related projects/storage.md --basis 'Compare the two recorded decisions'
co wiki review
co wiki review ID --verdict yes --author user --response 'Both require offline operation'
co wiki review ID --verdict no --author user --response 'Different constraints'
```

For a `question`, pass one subject and later `--verdict answer --response TEXT`.
Decisions are retained in `.state/reviews.json`; exact rejected candidates do not
reappear. Maintenance receives answered/accepted/rejected records as evidence.
Models can propose at most two candidates per pass. The reader's **Questions &
connections** section displays them and terminal commands; it is a read-only snapshot.

Optional local voice input requires **whisper.cpp's `whisper-cli`** and an already
downloaded local model. Nothing is downloaded or sent to a cloud transcriber:

```bash
co wiki review ID --verdict answer --author user \
  --audio answer.wav --local-model /path/to/ggml-base.bin
```

## Preserve sessions and run a daily round

```bash
co wiki capture /absolute/path/rollout.jsonl --source codex
co wiki capture /absolute/path/session.jsonl --source claude-code
co wiki daily --days 30
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

Normal sync still requires recorded source consent. Captured material and reflections
are drained only after a successful run; failed runs preserve the queue. This preview
does not implement cross-machine locking, external sharing permissions or automatic
factual adjudication. The underlying Markdown pages remain local.
