# A guard on the real ~/.co during the unit suite

2026-11-08, branch `sprint11/home-leak` (origin/main rc61 + 649bebd56).

## Why `_never_touch_the_real_home` missed it

`tests/conftest.py` imports `connectonion` at module level (`from connectonion import Agent`),
and each test file imports the modules it tests at collection. Both happen before any fixture
runs. `_never_touch_the_real_home` repoints `HOME` and `Path.home()` *per test*, which only
reaches code that asks for the home when it runs. A module constant asked once, at import, and
keeps the operator's real home for the whole run:

    connectonion/cli/commands/keys_commands.py:296  SSH_PRIVATE_KEY = Path.home() / ".co" / "ssh" / "id_ed25519"

`per_host_key_path()` built `SSH_PRIVATE_KEY.parent / f"id_ed25519_{host}"` (fixed in 649bebd56 to
ask `Path.home()` at call time), so `TestTheKeyPairOnDiskAlwaysMatches` and the staging test wrote
`~/.co/ssh/id_ed25519_{prod,staging}(.pub)` into the real home, green.

It is order dependent: if a module is first imported *inside* a test, the constant freezes that
test's tmp home instead. That is why running one file alone can look clean.

## Module-level constants built from the home

Grep of the package for unindented `Path.home()`, `expanduser(`, `os.environ["HOME"]`
(function-local uses resolve at call time and are not listed):

| file:line | constant | writes? | a test wrote the real home through it |
|---|---|---|---|
| `cli/commands/keys_commands.py:296-297` | `SSH_PRIVATE_KEY`, `SSH_PUBLIC_KEY` | no longer used by code since 649bebd56 | yes, before 649bebd56: `ssh/id_ed25519_prod`, `_staging` |
| `cli/commands/outlook_commands.py:35` | `INBOX_CACHE` (also `gmail_mailbox_commands.py:59` via `.parent`) | yes, `_remember_listing` | **yes**: `test_outlook_commands.py::TestOutlookDraftCommands::test_drafts_piped_lists_each_with_its_link` wrote `outlook_last_inbox.json` |
| `cli/co_ai/agent.py:79` | `GLOBAL_CO_DIR` | yes, `co ai`'s agent logs | **yes**: `test_one_host.py::test_co_ai_answers_each_channel_once_through_the_host` and `::test_co_ai_does_not_start_a_second_handoff_watcher` wrote `logs/oo.log` (hidden by the `logs/` allowance on a real home) |
| `cli/commands/outlook_commands.py:40` | `LISTINGS` | yes | not in this suite (every writer patches it) |
| `cli/commands/server_commands.py:29` | `SERVERS_FILE` | yes, + `.lock` | not in this suite |
| `cli/commands/remote_browser_commands.py:30` | `CONFIG_PATH` | yes | not in this suite |
| `cli/commands/proxy_commands.py:47` | `STATE_PATH` | yes | not in this suite |
| `cli/commands/sub_commands.py:54-56` | `CO_HOME`, `SUBS_DIR`, `SUBS_LIST` | yes | not in this suite |
| `cli/commands/fanout.py:24` | `HOME` (writes `~/.claude`, `~/.cursor`, `~/.kiro`, `~/.co/subscription-installs`) | yes | not in this suite |
| `network/host/ws_router/dashboard.py:29` | `STARTER_OVERRIDE` | read only | n/a |

"Not in this suite" means a strict scratch-home run found no write; every current writer test
patches the constant by hand, which is exactly what a future test forgets.

## What changed

- `tests/conftest.py`, session hooks: at `pytest_sessionstart` the controller (not xdist
  workers) records `{relative path: (size, mtime_ns, inode)}` of the real `~/.co` by `lstat` only
  — nothing is opened; directories are recorded as existing only. `pytest_sessionfinish`
  compares, sets the exit status to 1 on any created/changed/deleted path, and the terminal
  summary lists them. The real home is captured at conftest import, before any patch.
  Ignored (top level only): `browser`, `browser_profile`, `browser_context`, `browser_network`,
  `browser.log` (the `co browser` daemon) and `logs` (hosted agents and `co ai`). `ssh/`,
  `keys.env`, `rem/` are never ignored. `CONNECTONION_TEST_REAL_HOME=<dir>` points the guard at a
  scratch home and then ignores nothing.
- `tests/conftest.py`, `_never_touch_the_real_home`: every connectonion module-level `Path`
  under the real home is rebased onto the test's tmp home with `monkeypatch.setattr` (found by
  scanning `sys.modules`, rescanned only when new modules were imported). This fixes every row
  above at once, including constants added later; a test that patches one itself still wins.
  No product code changed: in production HOME does not move during a process.
- `tests/unit/test_cli_commands_ai_trust.py`: three assertions compared `co_dir` to the
  `GLOBAL_CO_DIR` the test module imported, i.e. asserted that `co ai` uses the *real* `~/.co`.
  They now assert `Path.home() / ".co"`, the isolated one.

## Red first

Guard, with 649bebd56's line reverted in a scratch copy, scratch "real" home, the failing
isolation test deselected so every collected test is green:

    ! the real <scratch>/fakehome.NOos/.co changed during this run !
    created: ssh
    created: ssh/id_ed25519_prod
    created: ssh/id_ed25519_prod.pub
    created: ssh/id_ed25519_staging
    created: ssh/id_ed25519_staging.pub
    85 passed, 1 deselected in 3.89s
    exit=1

Without the deselect `test_ssh_home_isolation.py` also fails (1 failed, 85 passed). With the fix
restored: `86 passed`, guard unchanged, exit 0.

Outlook cache, `tests/unit/test_outlook_commands.py`, before / after the rebasing:

    created: outlook_last_inbox.json
    59 passed in 2.83s
    exit=1
    ---
    real-home guard: <scratch>/.co unchanged
    59 passed in 2.09s
    exit=0

`co ai` logs, `test_cli_commands_ai_trust.py` + `test_one_host.py` (the first imports
`co_ai.agent` at collection), before / after:

    created: logs
    created: logs/oo.log
    32 passed in 6.84s
    exit=1
    ---
    real-home guard: <scratch>/.co unchanged
    32 passed in 6.92s
    exit=0

Full unit suite against a scratch home, strict: before the rebasing the guard listed
`logs`, `logs/oo.log`, `outlook_last_inbox.json`; after it, unchanged.

## Not fixed here

`import connectonion` loads the operator's real `~/.co/keys.env` into `os.environ`
(`connectonion/__init__.py:31`, `load_environment()`), before any fixture. Against a scratch home 18 unit tests fail, mostly with
`MissingAmbientAPIKey` (`test_admin_logs_reads_the_log_the_agent_writes.py`,
`test_agent_index.py::TestHostStartup`, `test_co_ai_hosts_a_factory.py`, ...): they pass on a
developer machine only because the real `OPENONION_API_KEY` is in the process. That
is a read of the real home, not a write, and needs its own issue.

## Final run on the real home

`env -u FORCE_COLOR uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit -n 6 --dist=worksteal`,
real HOME, from the worktree.

First attempt, 23:03–23:09, exit 1, every test green:

    !!!!!!!!!!!! the real /Users/changxing/.co changed during this run !!!!!!!!!!!!!
    changed: outlook_last_inbox.json
    changed: ssh/id_ed25519_prod
    changed: ssh/id_ed25519_prod.pub
    changed: ssh/id_ed25519_staging
    changed: ssh/id_ed25519_staging.pub
    18756 passed, 19 skipped, 2944 warnings in 326.29s (0:05:26)

Not written by this branch. Two other unit suites started in the same window from worktrees
that do not contain 649bebd56 (`per_host_key_path` still returns `SSH_PRIVATE_KEY.parent / ...`):
`/private/tmp/rem-sprint11/github-ingest` (5614a88b7, started 23:03:15) and
`/private/tmp/rem-sprint11/project-views` (c085c2e2d, 23:05:10). Those are exactly the paths the
unfixed `test_server_commands.py`/`test_ssh_home_isolation.py` and
`test_outlook_commands.py::TestOutlookDraftCommands::test_drafts_piped_lists_each_with_its_link`
write. The guard watches the directory, not the process, so it reports them correctly: the real
home *did* change during the run. Every run of a branch without these fixes will keep doing it
until they reach main.

Second run, after waiting until no other worktree's pytest was running, with a diagnostic audit
hook (scratch plugin, not committed) recording every in-process write under the real `~/.co`
with the current test id:

    real-home guard: /Users/changxing/.co unchanged
    18756 passed, 19 skipped, 2944 warnings in 151.68s (0:02:31)

The audit hook recorded no write.
