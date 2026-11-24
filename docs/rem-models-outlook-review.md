# REM models and Outlook sprint review — 2026-11-08

Branch: `sprint8/models-outlook`. Base and unchanged HEAD: `391186fbc9eef3355d6f66bbcb4fc50f78106d0f` (`origin/release/1.9.3rc60`). No commit made. The real `~/.co` notebook and credential files were used only as read-only evidence.

## Changes by requested item

1. `connectonion/rem/config.py:40` defaults REM work to `gpt-6.1-sol`; `models.summary` defaults to `gpt-6-luna` for Codex, is validated and settable using `co rem config set models.summary VALUE`. `config.py:152` migrates saved superseded Luna defaults on read; EXPLICIT choices remain. No config is rewritten during inspection. `sessions.py:829` uses a copied config with the summary model only for standalone coding-session summary calls, including init/import/sync/daily callers. Their saved model and run records report the actual summary model. Non-Codex notebooks keep their working model for summaries until a summary model is chosen, and the Claude fallback stays compatible (`config.py:196`, `:236`, `:288`).
2. `connectonion/rem/native.py:51` excludes model/speed/effort/models.summary from task material identity. `native.py:73` and `:78` reproduce rc59/rc60 semantic and raw-file digests using saved stage configuration, or the unchanged saved file where no stage snapshot exists. Evidence-sizing changes still reject. Missing config rejects safely. Authentic pre-split fixtures cover Luna migration and absent snapshots.
3. `connectonion/rem/service.py:701`, `connectonion/cli/commands/rem_status.py:39`, and `rem_commands.py:2181` show one model-role line in status/config. Help documents the setting and compatible fallback.
4. `connectonion/environment.py:123`, `connectonion/rem/codex_exec.py:189`, and `runner.py:142` stop exporting managed OAuth records as process overrides. Children reread the selected credential file, keeping refresh locks, rotation recovery and atomic persistence. Explicit process overrides remain. `runner.py:110` forwards an explicit env-file selector and `native.py:365` includes it in printed submit commands. `service.py:1291` / `:1307` preserve sanitized ProviderCredentialError code, message and Next command while continuing to redact arbitrary exception text. Coverage includes reauth_required, broker_auth_failed, record_changed, invalid_response and permission_denied.

## Outlook diagnosis and limits

The real notebook records the class-only Outlook failure at 2026-11-07T02:44:14Z, while Outlook remains enabled and consented. The round is still pending, so continuation resumes its saved work instead of recollecting every source. `native_round.py:26` collects sources when a fresh round starts; `service.py:1395` rotates eligible sources and a failure advances rotation without advancing that mailbox's checkpoint. `source_reads.json` is status evidence, not a circuit breaker. Outlook is eligible for later rounds; one failure does not disable it.

The launcher already grants the selected env directory. Refresh's lock, rotation journal, temp file and atomic replacement all live beside that env file. The owner's keys.env is a regular file under ~/.co, so that grant covers these writes. A filesystem denial would be an OSError/PermissionError rather than one of the broker error codes.

A reproducible launcher defect was found: load_environment publishes file-backed OAuth tokens to os.environ, and exporting those tokens to a fresh process loses their provenance. The child treats them as explicit process credentials (path=None), bypassing rereading, file refresh locks, rotation recovery and persistence. This explains how a scheduled session can diverge from a fresh manual CLI. Tests reproduce the defect and the corrected selected-file resolution without touching real credentials. **The historical provider code cannot be uniquely recovered from the class-only saved record; it is not proved which of reauth_required/broker_auth_failed/record_changed/invalid_response occurred on that turn.** No real Outlook request, refresh, or credential rewrite was performed.

Native scheduled session summaries remain inline in the main work-model session (`native_round.py:167`). Splitting them needs an explicit execution handoff: next/submit deliberately perform no model calls, with existing tests enforcing that contract. This was left out rather than silently adding model calls to those boundaries. Native summaries therefore use the work model, while standalone summary calls use models.summary. Source extraction digests, page synthesis, audits, translations and replies retain their work-model configuration; the shared runner stage named abstract is not used as a routing shortcut.

## Independent AI founder/UI review

The independent reviewer inspected actual rendered CLI config/status on isolated fictional notebooks: disconnected/default state, Claude fallback, Outlook reauth_required, broker_auth_failed and permission_denied. They also rendered config/import help and executed old-digest and explicit-selector reproductions. P1 findings (old snapshotless digests, explicit account selection, Claude fallback) and P2 permission-recovery loss were fixed and rechecked. Recheck criteria: unchanged old task accepts while evidence changes reject; selected account path survives a child process; model roles fit one line; Outlook state retains code/message/Next action. No significant findings remain in this inspected scope.

Not inspected: live mailbox refresh, paid model calls, browser reader/mobile flows (unchanged). Process-tree deadline cleanup cannot be verified in this sandbox because ps is blocked. The exact same two cleanup tests fail with HEAD's unchanged _execute implementation.

## Test commands and exact final lines

All ordinary commands use this prefix:

```sh
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider
```

### Initial regression red

Arguments: `tests/unit/test_rem_config.py tests/unit/test_rem_exec_startup.py tests/unit/test_rem_service.py tests/unit/test_rem_next_submit.py tests/unit/test_rem_sessions.py -k 'old_luna or summary_model or model_roles or pre_model_split or run_control_config or source_read_preserves or scheduled_child_rereads or a_new_notebook_runs_on_codex or rc59_semantic' -n 6`. [Full log](/tmp/rem-sprint8-red.log).

Exact last line:

```text
24 failed, 34 passed, 198 warnings in 29.66s
```

### First focused rerun

Arguments: `same arguments as initial regression red`. [Full log](/tmp/rem-sprint8-green.log).

Exact last line:

```text
1 failed, 57 passed, 276 warnings in 28.21s
```

### Review regressions red

Arguments: `tests/unit/test_rem_next_submit.py tests/unit/test_provider_credentials.py -k 'old_semantic_digest_without or rem_child_keeps_selected' -n 6`. [Full log](/tmp/rem-sprint8-review-red.log).

Exact last line:

```text
3 failed, 2 passed in 15.50s
```

### Permission recovery red

Arguments: `tests/unit/test_rem_service.py -k 'source_read_preserves and permission_denied'`. [Full log](/tmp/rem-sprint8-permission-red.log).

Exact last line:

```text
1 failed, 158 deselected in 7.47s
```

### First required suite

Arguments: `tests/unit/test_rem_exec*.py tests/unit/test_rem_config*.py tests/unit/test_rem_next_submit.py tests/unit/test_rem_service*.py tests/unit/test_provider_credentials*.py -n 6`. [Full log](/tmp/rem-sprint8-required.log).

Exact last line:

```text
3 failed, 509 passed, 1498 warnings in 120.89s (0:02:00)
```

### Fallback compatibility red

Arguments: `tests/unit/test_rem_config.py -k 'summary_default_stays or runner_change_keeps_summary'`. [Full log](/tmp/rem-sprint8-fallback-red.log).

Exact last line:

```text
2 failed, 17 deselected in 3.99s
```

### Additional complete files

Arguments: `tests/unit/test_rem_config.py tests/unit/test_rem_sessions.py tests/unit/test_provider_credentials.py -n 6`. [Full log](/tmp/rem-sprint8-additional.log).

Exact last line:

```text
202 passed in 26.44s
```

### Unchanged base cleanup tests

Arguments: `baseline harness below`. [Full log](/tmp/rem-sprint8-baseline.log).

Exact last line:

```text
2 failed, 22 deselected in 9.48s
```

### Final required suite

Arguments: `same arguments as first required suite`. [Full log](/tmp/rem-sprint8-required-final.log).

Exact last line:

```text
2 failed, 512 passed, 1498 warnings in 80.08s (0:01:20)
```

### Missing-config regression red

Arguments: `tests/unit/test_rem_next_submit.py -k missing_config_refuses_saved_digest`. [Full log](/tmp/rem-sprint8-missing-red.log).

Exact last line:

```text
1 failed, 264 deselected in 12.35s
```

### Final focused green

Arguments: `tests/unit/test_rem_next_submit.py tests/unit/test_rem_config.py tests/unit/test_rem_sessions.py tests/unit/test_provider_credentials.py -k 'missing_config_refuses_saved_digest or old_semantic_digest_without or pre_model_split or rc59_translation or run_control_config or summary_model or summary_default_stays or runner_change_keeps_summary or rem_child_keeps_selected or model_roles or old_luna' -n 6`. [Full log](/tmp/rem-sprint8-final-focused.log).

Exact last line:

```text
55 passed, 252 warnings in 22.28s
```

The first focused rerun's remaining failure was a test fixture choosing the Claude fallback while asserting Sol; the summary test now explicitly selects Codex/Sol. The first required suite's extra translation failure was a fixture generating a new hash while naming it rc59; it now requests the historical model-inclusive digest and additional literal pre-split fixtures cover genuine old files. Final required failures are exclusively the two sandbox-blocked cleanup tests.

Baseline harness (uses repository HEAD source in memory, no checkout mutation):

```python
import subprocess
import types
import pytest
from connectonion.rem import codex_exec
baseline = types.ModuleType('connectonion.rem._sprint8_baseline')
baseline.__package__ = 'connectonion.rem'
exec(subprocess.check_output(['git', 'show', 'HEAD:connectonion/rem/codex_exec.py'], text=True), baseline.__dict__)
codex_exec._execute = baseline._execute
raise SystemExit(pytest.main(['-q', '-p', 'no:cacheprovider', 'tests/unit/test_rem_exec_schedule.py', '-k', 'deadline_kills_detached_grandchild']))
```

`git diff --check` passes. Regression red runs were executed before their corresponding fixes; final full and focused runs cover their accepted and rejection behavior. No tests required live owner data.
