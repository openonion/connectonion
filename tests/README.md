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
| `_never_touch_the_real_home` | HOME and `~/.co` are a fresh tmp dir per test | A test overwrote a live Outlook token with a fake one |
| `_no_stray_project_above_the_test` | A `.co/` above the working directory is a failure, not a wrong answer | Unit tests reading `/private/tmp/.co` |
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

`.github/workflows/tests.yml` runs `pytest -n auto` on Python 3.10 to 3.13
with a 15 minute job timeout, measures coverage on 3.12 and fails below the
floor set there (raise it as coverage rises, never lower it to pass), and
runs the platform-specific browser and transport suites on Windows and macOS.
