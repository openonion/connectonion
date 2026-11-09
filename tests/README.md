# ConnectOnion tests

Two layers, unit and e2e, one config file (`pytest.ini`), one way to run them.
See [TEST_ORGANIZATION.md](./TEST_ORGANIZATION.md) for where a new test goes.

```
tests/
├── conftest.py               # policy fixtures (below) + shared fixtures
├── unit/                     # one source file, dependencies mocked   → marker: unit
├── e2e/                      # a real flow end to end                 → marker: e2e
│   ├── cli/                  # real `co` invocations                  → + cli
│   ├── real_api/             # paid providers, real accounts          → + real_api
│   └── manual/               # demo scripts, not collected
├── fixtures/                 # shared test data
└── utils/                    # MockLLM, ProjectHelper, ...
```

## Running

```bash
pip install -e ".[dev]"

make test                 # everything offline, all cores, ~1 minute
pytest tests/unit/test_agent.py            # one file, in-process (use -s, breakpoints)
pytest -k "the_name_of_a_test"             # one test
make test-e2e             # our own system end to end (relay included)
make test-real            # paid providers; needs keys and money
make cov                  # `make test` plus the coverage report CI gates on
```

The default selection is `not real_api and not network`. A `-m` on the
command line replaces that expression rather than adding to it, so spell the
whole thing out when you narrow further (the Makefile does).

## What the suite enforces on every test

These live in `tests/conftest.py` as autouse fixtures. Each one exists because
the thing it forbids happened and cost a day.

| Guard | What it does | What it caught |
|---|---|---|
| `_no_network` | Refuses any socket that leaves the machine; points the backend URL at a dead port; fails the test in teardown naming the host | 57 tests hitting production on every run; a test that hung CI for 300s on an LLM call with key `test-key` |
| `_no_leaked_threads` | A thread still alive after the test fails it, by name | 39 `registry-cleanup` threads leaked by four modules, which later starved the main thread until the timeout (#1246) |
| `_never_touch_the_real_home` | HOME and `~/.co` are a fresh tmp dir per test, and every connectonion module-level `Path` under the real home (a constant built from `Path.home()` at import) is rebased onto it | A test overwrote a live Outlook token with a fake one; a run wrote per-server SSH keys into the real `~/.co/ssh` through a frozen constant |
| real-home guard (`tests/real_home_guard.py`) | An audit hook in every pytest process records each write under the real `~/.co` with the running test's id; any record fails the run, naming test and path, with no allowlist. At the end the controller also runs one `find -cnewer` pass over the real `~/.co` (lstat only, never opening a file) for every entry whose ctime moved during the run, in-place appends included: a change no record explains is printed as "changed by another process" with the likely writer (REM turns in the window, live `co`/`codex` processes), and does not fail — the owner's machine writes `keys.env`, REM state and mail stores while tests run. A change under `ssh/` is printed loudly but also does not fail: `co server`/`co keys` write there legitimately, and a test's subprocess is invisible to the hook. A pytest started inside a running pytest (`CONNECTONION_REAL_HOME_GUARD_OWNER` names a live owner) keeps the hook, writing to the owner's records so the owner goes red, but skips the pass over `~/.co`. `CONNECTONION_TEST_REAL_HOME=<scratch dir>` points it at a scratch home; `tests/unit/test_real_home_guard_watches_the_account_home.py` plants writes there | `ssh/id_ed25519_prod`, `id_ed25519_staging`, `outlook_last_inbox.json` and `logs/oo.log` written into a scratch "real" home by green runs |
| `_no_stray_project_above_the_test` | A `.co/` above the working directory is a failure, not a wrong answer | Unit tests reading `/private/tmp/.co` |
| `_nothing_written_into_the_repos_own_project` | An audit hook fails any test that writes under the repository's own `.co/`, naming the paths; use the `own_project` fixture (a tmp working directory) instead | ~90 tests in 17 files writing evals, logs, `admins.txt` and a session store into the checkout, shared by every xdist worker |
| `_restore_excepthook` | `sys.excepthook` installed by a test does not outlive it | |
| `_isolate_selected_environment` | Provider selection cannot leak between tests | |
| import time | `FORCE_COLOR` and friends are stripped so output matches CI | 43 local-only failures from ANSI codes in asserted text |

Plus, from `pytest.ini`: a 60s timeout per test (hangs get a thread dump
naming the test), `xfail_strict`, `--strict-markers`, and `-ra` so every
non-pass outcome is listed at the end.

A test that genuinely needs the network marks itself `network` (our relay) or
`real_api` (paid providers) and is left out of the default run. A test that
needs longer than 60s marks itself `@pytest.mark.timeout(N)`. A test about
backend URL resolution requests the `default_backend_url` fixture.

## Writing a test

- Unit: one source file, everything else mocked. `MockLLM` from
  `tests/utils/mock_helpers.py` stands in for a model; `ProjectHelper` from
  `tests/utils/config_helpers.py` gives you a throwaway project directory.
- Assert on behaviour the user would see (output, files, calls made), not on
  `_private` state or `len(plugins) == N`.
- If it starts a thread, a server, or a browser, stop it in the same test.
- A regression test is written to fail on the unfixed code first.

## CI

`.github/workflows/tests.yml` runs `pytest -n auto` on Python 3.11 to 3.13,
each as six parallel shards with a 15 minute timeout per shard.
`scripts/ci_test_shard.py` splits the test files between shards, balanced by
`tests/ci_durations.json`; a new file weighs the median until the weights are
refreshed with `python scripts/ci_test_shard.py --record junit-3.11-*/junit.xml`
from a run's `junit-*` artifacts. Inside a shard, `--dist worksteal` hands out
single tests, as `make test` does. The 3.12 shards trace coverage through
`COVERAGE_CORE=sysmon`; the `coverage` job combines them and fails below the
floor set there (raise it as coverage rises, never lower it to pass).

The `co --help` audit (`tests/unit/test_cli_help_contract.py`) runs as six
`cli-help-audit` shards, each walking and auditing the top-level commands
that fall to it; `cli-help-audit-tree` then checks the whole tree once over
every shard's list of pages. `tests-passed` is green only when every shard,
the coverage gate and both audit jobs succeeded. The workflow also runs the
platform-specific browser and transport suites on Windows and macOS.

Background-task termination also reaps the owned shell process tree and joins
its output reader. A termination confirmation must not leave a live reader or
an open stdout pipe. Missing-skill diagnostics preserve full paths when piped,
including paths longer than the terminal width.
