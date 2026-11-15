# Validate the single-vault draft

Run from the single-vault worktree with its package on `PYTHONPATH` and the existing
project virtual environment first on `PATH`. The commands below are a reusable
validation procedure, not a transcript of every action in the author's demo.

## Recorded local validation on 2026-11-15

The author reported that the six targeted source/integration test files and the
four CLI audits below passed. The broader REM regression initially reported
12 failed and 6544 passed. After adapting three mocks for the notebook-root
argument and one callback-identity assertion for the approval wrapper,
`test_rem_investigate.py`, `test_rem_runner.py` and
`test_rem_obsidian_integration.py` passed on rerun.

Eight failures remain unresolved: seven Reader date-format assertions and one
fixed-date session-import fixture outside its relative lookback window. They
appear locale/date-dependent but have not been reproduced on a clean upstream
baseline. The full regression is not claimed to pass.

The author's live walkthrough completed initial collection of 14 notes, a new-note
sync, a no-change sync, and a subsequent sync with one modification and one addition.
A separate Reader-context check returned both saved versions of note A and note B's
checklist. An investigation with `--days 1` gathered two saved notes and accepted a
page update. Source removal and scheduler shutdown both returned `Enabled: No`.
The supplied removal screenshots do not independently verify post-removal citation
denial or vault-file preservation; step 10 below remains a procedure for that check.

The shared investigation runner also retrieved Codex-session material and searched
the web, despite other subscriptions being disabled. Its final page retained mixed
Obsidian/Codex citations and unresolved status statements. This is not evidence of
Obsidian-only tool execution or complete factual correctness. No tests or model
calls were run by the implementation agent during submission-scope review.

## 1. Automated source and integration tests

```bash
python -m pytest -q \
  tests/unit/test_rem_obsidian.py \
  tests/unit/test_rem_obsidian_store.py \
  tests/unit/test_rem_obsidian_source.py \
  tests/unit/test_rem_source_hooks.py \
  tests/unit/test_rem_source_versions.py \
  tests/unit/test_rem_obsidian_integration.py
```

These use synthetic vaults and mocked model execution. Include the final summary
in one screenshot. A failure is a reason to stop and fix, not to remove a test.

## 2. Regression tests

```bash
python -m pytest -q \
  tests/unit/test_rem_*.py \
  tests/unit/test_obsidian.py \
  tests/unit/test_obsidian_commands.py \
  tests/unit/test_gmail_listing_context.py \
  tests/unit/test_gdrive_listing_context.py
```

This broader set covers the existing REM callers changed by the integration, plus
CLI listing isolation. It is a focused REM regression, not the entire repository
suite. Keep its final summary separately from the new-source result.

## 3. CLI smoke and help audit

```bash
co rem sources add --help
co rem sync --help
co obsidian --help
co audit co obsidian
co audit co rem sources
co audit co rem start
co audit co rem sync
```

Check that add shows vault/folder/replace, sync shows source/dry-run, and Obsidian
still has read-only commands. The audit verifies command help, not real model
behavior or source privacy. An optional `--review` does not replace the tests.
No benchmark suite is introduced in this change; a full benchmark is not a substitute
for the following first-sync, no-change and exact-version checks.

## 4. Real local demo: select the subscription set

Use a new notebook outside the vault. Set `OBSIDIAN_DEMO_VAULT` to the actual vault
path and `OBSIDIAN_DEMO_FOLDER` to the desired existing folder. These example paths
are placeholders; the shell variables must stay set across the following steps.

```bash
export OBSIDIAN_DEMO_VAULT='/Users/example/Vault'
export OBSIDIAN_DEMO_FOLDER='Work'
export OBSIDIAN_REM_DEMO="$(mktemp -d /tmp/obsidian-rem-demo.XXXXXX)"

co rem --root "$OBSIDIAN_REM_DEMO" sources remove codex
co rem --root "$OBSIDIAN_REM_DEMO" sources remove claude-code
co rem --root "$OBSIDIAN_REM_DEMO" sources remove gmail
co rem --root "$OBSIDIAN_REM_DEMO" sources remove outlook
co rem --root "$OBSIDIAN_REM_DEMO" sources remove whatsapp
co rem --root "$OBSIDIAN_REM_DEMO" sources add obsidian --vault "$OBSIDIAN_DEMO_VAULT" --folder "$OBSIDIAN_DEMO_FOLDER"
co rem --root "$OBSIDIAN_REM_DEMO" sources
```

Verify the active set before any acquisition. Default disabled rows may still be
listed: removing subscriptions does not delete the provider names from the UI.
This checks source subscriptions, not isolation of the investigation runner's tools.

```bash
python - <<'PY'
import os
from pathlib import Path
from connectonion.rem.service import subscriptions
root = Path(os.environ['OBSIDIAN_REM_DEMO'])
active = sorted(name for name, sub in subscriptions(root).items()
                if sub.get('enabled') and not sub.get('unsubscribed'))
print('Active sources:', active)
assert active == ['obsidian'], active
PY
co rem --root "$OBSIDIAN_REM_DEMO" sync --source obsidian --dry-run
```

Screenshot A: only Obsidian active and dry-run awaiting approval. This uses the
real vault configuration but should not create the snapshot database yet.

## 5. Verify refusal of silent noninteractive approval

Run this only in the fresh notebook from step 4, before any successful start.
The current interactive CLI prints its summary and records approval directly;
it does **not** ask a y/n question. Do not run interactive start expecting to
answer n. Its invocation is the approval action in this version.

```bash
co rem --root "$OBSIDIAN_REM_DEMO" start </dev/null
```

With no prior approval and no `--yes`, this must report that a noninteractive run
cannot consent silently and exit unsuccessfully. Screenshot B covers that boundary,
not an interactive rejection. If the notebook has already been approved, skip this
step: it no longer proves the pre-approval boundary. Do not erase its consent or
snapshots just to recreate the screenshot.

## 6. Create one new demo note; approve and sync

This script creates a unique new note. It does not overwrite an existing note.
It simulates an external Obsidian edit; the CLI itself remains read-only.

```bash
python - <<'PY'
import json, os, uuid
from pathlib import Path
root = Path(os.environ['OBSIDIAN_REM_DEMO'])
vault = Path(os.environ['OBSIDIAN_DEMO_VAULT'])
folder = Path(os.environ['OBSIDIAN_DEMO_FOLDER'])
relative = folder / ('REM smoke ' + uuid.uuid4().hex[:12] + '.md')
body = '# REM Obsidian Smoke\n\nThe demo delivery colour is amber.\n'
with (vault / relative).open('x', encoding='utf-8') as stream:
    stream.write(body)
(root / 'demo-note.json').write_text(json.dumps({'path': relative.as_posix(), 'before': body}), encoding='utf-8')
print('Created:', relative)
PY
co rem --root "$OBSIDIAN_REM_DEMO" start
co rem --root "$OBSIDIAN_REM_DEMO" stop
co rem --root "$OBSIDIAN_REM_DEMO" sync --source obsidian --all
```

Review the scope before invoking interactive start. It records approval without
a y/n prompt and can invoke the configured model and install a schedule. Run stop immediately after start returns, including if the
first batch fails, to leave this demo manual. The final sync processes the remaining
selected notes using the model and its usage quota. A large selected folder can need
several batches; reaching a daily cap is not proof that all pending notes were consumed.

Screenshot C: acquisition counts and successful first batch/backfill. Existing folder
notes are included too, so the expected initial count is not necessarily one.

## 7. Verify no-change and save the exact first version

```bash
co rem --root "$OBSIDIAN_REM_DEMO" sync --source obsidian
python - <<'PY'
import json, os
from pathlib import Path
from connectonion.rem import obsidian_store, source_hooks
root = Path(os.environ['OBSIDIAN_REM_DEMO'])
info = json.loads((root / 'demo-note.json').read_text())
rows = [row for row in obsidian_store.latest_snapshots(root) if row['note']['path'] == info['path']]
assert len(rows) == 1
info['old_id'] = rows[0]['source_id']
assert source_hooks.cited(root, info['old_id'])['excerpt'] == info['before']
(root / 'demo-note.json').write_text(json.dumps(info), encoding='utf-8')
print('Saved old citation:', info['old_id'])
PY
```

Screenshot D: no new batch after the backlog is consumed. If material remains pending
or a quota stops processing, do not label the result as no-change.

## 8. Change only the demo note; verify both versions

```bash
python - <<'PY'
import json, os
from pathlib import Path
root = Path(os.environ['OBSIDIAN_REM_DEMO'])
info = json.loads((root / 'demo-note.json').read_text())
path = Path(os.environ['OBSIDIAN_DEMO_VAULT']) / info['path']
assert path.read_text(encoding='utf-8') == info['before'], 'Demo note changed unexpectedly'
path.write_text(info['before'].replace('amber', 'blue'), encoding='utf-8')
print('Changed only:', info['path'])
PY
co rem --root "$OBSIDIAN_REM_DEMO" sync --source obsidian
python - <<'PY'
import json, os
from pathlib import Path
from connectonion.rem import obsidian_store, reader_model
root = Path(os.environ['OBSIDIAN_REM_DEMO'])
info = json.loads((root / 'demo-note.json').read_text())
new_id = next(row['source_id'] for row in obsidian_store.latest_snapshots(root)
              if row['note']['path'] == info['path'])
assert new_id != info['old_id']
page = '\n## Sources\n- [1] ' + info['old_id'] + '\n- [2] ' + new_id + '\n'
contexts = reader_model.cited_context(root, [{'text': page}])
assert contexts[info['old_id']]['excerpt'] == info['before']
assert contexts[new_id]['excerpt'] == info['before'].replace('amber', 'blue')
for version in (info['old_id'], new_id):
    print(version, '\n', contexts[version]['excerpt'])
PY
```

Screenshot E: incremental acquisition and reader contexts showing amber versus blue.
This tests the reader context function with a synthetic citation list; it does not
claim the model generated those citations. The next step tests actual generated pages.

## 9. Real investigation (model-backed, separate screenshot)

```bash
co rem --root "$OBSIDIAN_REM_DEMO" stub project 'REM Obsidian Smoke'
co rem --root "$OBSIDIAN_REM_DEMO" investigate projects/rem-obsidian-smoke.md --handle 'REM Obsidian Smoke' --days 1
co rem --root "$OBSIDIAN_REM_DEMO" show projects/rem-obsidian-smoke.md
```

Screenshot F: actual investigation coverage/result, with exact source IDs on the
kept page if generated. Preserve a refusal or missing-evidence result rather than
claiming success. The live model can produce different wording. This step may use
additional model turns, even with only one source.
Use the stub command only if the target page does not already exist. The one-day
window covers newly created demo notes; older saved notes may be excluded.
The shared runner can perform independent retrieval, so retain all source types
in the evidence and do not describe this as an Obsidian-only investigation.

## 10. Withdraw the source

```bash
co rem --root "$OBSIDIAN_REM_DEMO" sources remove obsidian
co rem --root "$OBSIDIAN_REM_DEMO" sources
python - <<'PY'
import json, os
from pathlib import Path
from connectonion.rem import reader_model
root = Path(os.environ['OBSIDIAN_REM_DEMO'])
info = json.loads((root / 'demo-note.json').read_text())
page = '\n## Sources\n- [1] ' + info['old_id'] + '\n'
assert info['old_id'] not in reader_model.cited_context(root, [{'text': page}])
path = Path(os.environ['OBSIDIAN_DEMO_VAULT']) / info['path']
assert path.read_text(encoding='utf-8') == info['before'].replace('amber', 'blue')
print('Citation blocked after removal; demo note is unchanged.')
PY
```

Screenshot G: removal blocks new citation access and leaves the live note intact.
Keep the demo notebook and uniquely created note until review; remove only those
explicit demo artifacts later if desired. Never delete the original vault or folder.


## Demo troubleshooting: unsupported model

If the output says `Started: Yes`, `Consented: Yes` and the model call failed,
the source may already have been collected and the schedule installed. Stop the
demo schedule first. Do not describe that run as a rejected approval or a successful
end-to-end test. An acquisition result and model-stage result are separate evidence.
Change only the demo notebook's model to one supported by the logged-in runner
(the error may suggest a model). Config set can probe the model. After creating the
demo note, start again to approve the changed summary, stop the schedule, then run
explicit sync. A repeated start need not run the initial batch again.
